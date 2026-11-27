"""Full-width iterative Alpha-Beta with a bounds-checked transposition table.

V4 removes the duplicated move generations that dominated node cost:

* legality is checked in O(path) instead of comparing against a freshly generated
  move list;
* the terminal test uses ``has_any_move`` instead of building every move;
* the repetition test is a key lookup instead of a full ``check_winner`` call;
* scores are cached only when the subtree contained no repetition hit.

Nothing here changes which moves are legal or how a game is won.
"""
from functools import lru_cache
from math import inf
from time import perf_counter

from config.experimental import SearchOptions
from config.settings import DIRECTIONS
from config.evolution import BASE_WEIGHTS
from src.evaluation import WeightedEvaluator
from src.game import apply_move, check_winner, get_legal_moves, get_state_key
from src.transposition import EXACT, LOWER, UPPER, MATE_BOUND, MATE_SCORE, TranspositionTable
WIN_SCORE = MATE_SCORE


class SearchTimeout(Exception):
    """Discard an incomplete search iteration."""
from src.tactics import opponent, is_urgent, prioritize


DEFAULT_EVALUATOR = WeightedEvaluator(BASE_WEIGHTS)


def evaluate(board, side):
    return DEFAULT_EVALUATOR(board, side)


class EnhancedSearch:
    """One decision's state, including a bounded transposition table."""

    def __init__(self, side, deadline, evaluator, options, stats, node_budget=0):
        self.side = side
        self.deadline = deadline
        self.evaluator = evaluator
        self.options = options
        self.stats = stats
        self.table = TranspositionTable(options.tt_capacity)
        self.hints = self.table
        self.node_budget = node_budget or options.node_budget
        self.repetition_hits = 0
        self.children = lru_cache(maxsize=4096)(apply_move)
        self.root_preferred = set()
        self.root_draw_moves = set()
        self.killers = {}
        self.history_scores = {}

    def check_time(self):
        if perf_counter() >= self.deadline:
            raise SearchTimeout()

    def _adjacent_enemy(self, board, row, col, side):
        enemies = "DK" if side == "A" else "A"
        size = len(board)
        return any(0 <= row + dr < size and 0 <= col + dc < size
                   and board[row + dr][col + dc] in enemies for dr, dc in DIRECTIONS)

    def order(self, board, side, moves, ply):
        if not self.options.order_moves:
            return moves
        key = get_state_key(board, side)
        hint = self.table.get(key)
        if hint in moves:
            self.stats["tt_hint_hits"] += 1
        killer = self.killers.get(ply)
        size = len(board)
        root_preferred = self.root_preferred
        draw_moves = self.root_draw_moves if ply == 0 else ()
        history_scores = self.history_scores
        target = ply == 0

        def priority(move):
            (row, col), (r, c) = move
            # Tie-break, never a score rule: among equally scored root moves the ones
            # that would repeat a position immediately are searched last.
            return (target and move in root_preferred,
                    move not in draw_moves,
                    board[row][col] == "K" and (r in (0, size - 1) or c in (0, size - 1)),
                    move == hint,
                    move == killer,
                    history_scores.get((side, move), 0))

        return sorted(moves, key=priority, reverse=True)

    def visit(self, board, side, depth, alpha, beta, history, ply=0, moves=None):
        self.check_time()
        self.stats["nodes"] += 1
        if self.node_budget and self.stats["nodes"] > self.node_budget:
            raise SearchTimeout()
        key = get_state_key(board, side)
        if key in history:
            self.repetition_hits += 1
            return 0.0, ()
        terminal = check_winner(board, side)
        self.check_time()
        if terminal is not None:
            if terminal == "DRAW":
                return 0.0, ()
            # Mate distance: prefer the shorter win and the longer loss.
            distance = WIN_SCORE - ply
            return (distance if terminal == self.side else -distance), ()
        if depth == 0:
            score = self.evaluator(board, self.side)
            self.check_time()
            return score, ()

        cached = self.table.probe(key, depth, alpha, beta, ply)
        if cached is not None:
            move = self.table.get(key)
            return cached, ((move,) if move else ())

        ancestors = history + (key,)
        maximizing = side == self.side
        best, pv = (-inf if maximizing else inf), ()
        if moves is None:
            moves = get_legal_moves(board, side)
        alpha_start, beta_start = alpha, beta
        repetitions_before = self.repetition_hits
        for move in self.order(board, side, moves, ply):
            self.check_time()
            child = self.children(board, move, side)
            score, tail = self.visit(child, opponent(side), depth - 1,
                                     alpha, beta, ancestors, ply + 1)
            if (maximizing and score > best) or (not maximizing and score < best):
                best, pv = score, (move,) + tail
            if maximizing:
                alpha = max(alpha, best)
            else:
                beta = min(beta, best)
            if alpha >= beta:
                self.stats["cutoffs"] += 1
                if self.options.order_moves:
                    _, (r, c) = move
                    if not self._adjacent_enemy(board, r, c, side):
                        self.killers[ply] = move
                    self.history_scores[(side, move)] = self.history_scores.get((side, move), 0) + depth ** 2
                break
        self.check_time()
        if pv and self.repetition_hits == repetitions_before:
            # Bounds must be compared with the window this node was entered with.
            flag = LOWER if best >= beta_start else UPPER if best <= alpha_start else EXACT
            self.table.store(key, depth, best, flag, pv[0], ply)
        return best, pv


def choose_enhanced(board, side, *, deadline, soft_deadline=None, history=(),
                    evaluator=None, stats=None, options=None, moves=None):
    options = SearchOptions() if options is None else options
    board = tuple(map(tuple, board))
    history = tuple(history)
    moves = get_legal_moves(board, side) if moves is None else moves
    stats = {} if stats is None else stats
    stats.update(target_depth=options.max_depth, completed_depth=0, nodes=0, cutoffs=0,
                 tt_hint_hits=0, root_moves=len(moves), timed_out=False,
                 fallback_used=False, score=None, pv=[], finish_reason="no_legal_moves", tactical_status="not_checked")
    if not moves:
        return None
    preferred = ()
    now = perf_counter()
    if now < deadline and is_urgent(board):
        if options.node_budget:
            # Deterministic diagnostic: bounded by generated children, not by wall clock.
            moves, info = prioritize(board, side, moves, inf, history, max_nodes=200)
        else:
            # Bound diagnostic work to 10ms or 5% of the remaining step budget.
            moves, info = prioritize(board, side, moves, min(deadline, now + min(.010, (deadline - now) * .05)), history)
        stats["tactical_status"] = "complete" if info.status_complete else "unknown"
        if info.status_complete and info.opponent_threat_now:
            preferred = info.safe_replies
        if info.immediate_wins:
            move = info.immediate_wins[0]
            stats.update(score=WIN_SCORE - 1, pv=(move,), finish_reason="tactical_win")
            return move
    best = moves[0]
    search = EnhancedSearch(side, deadline, evaluator or evaluate, options, stats)
    search.root_preferred = set(preferred)
    if history:
        # A root move whose resulting position already occurred is an instant draw.
        # It stays legal and is never banned; it only loses tie-breaks (see order()).
        other = opponent(side)
        search.root_draw_moves = {move for move in moves
                                  if get_state_key(apply_move(board, move, side), other) in history}
        stats["root_draw_moves"] = len(search.root_draw_moves)
    stats["finish_reason"] = "depth_completed"
    for depth in range(1, options.max_depth + 1):
        if perf_counter() >= deadline:
            stats.update(timed_out=True, fallback_used=True, finish_reason="search_deadline")
            break
        if soft_deadline is not None and perf_counter() >= soft_deadline:
            stats.update(fallback_used=True, finish_reason="soft_deadline")
            break
        try:
            score, pv = search.visit(board, side, depth, -inf, inf, history, moves=moves)
        except SearchTimeout:
            stats.update(timed_out=True, fallback_used=True, finish_reason="search_deadline")
            break
        if not pv:
            stats["finish_reason"] = "terminal_position"
            return None
        best = pv[0]
        stats.update(completed_depth=depth, score=score, pv=pv)
        if abs(score) >= MATE_BOUND:
            stats["finish_reason"] = "proven_terminal"
            break
    return best
