"""Full-width iterative Alpha-Beta with a bounds-checked transposition table.

V4 removes the duplicated move generations that dominated node cost:

* legality is checked in O(path) instead of comparing against a freshly generated
  move list;
* the terminal test uses ``has_any_move`` instead of building every move;
* terminal wins precede repetition draws;
* cached scores require the same repetition context and no repetition hit.

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
from src.tactics import (attacker_move_priority, immediate_escape_count, is_urgent,
                         opponent, prioritize, prove_capture, structure_state)


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
        self.root_strategy_ranks = None
        self.root_scores = {}
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

    def _compute_root_strategy(self, board, side, moves):
        """One-shot attacker ordering table, capped at 5% of the remaining step budget."""
        if self.root_strategy_ranks is not None:
            return self.root_strategy_ranks
        start = perf_counter()
        limit = start + min(max(0.0, (self.deadline - start)) * 0.05, 0.25)
        escapes_before = immediate_escape_count(board)
        completion_before = structure_state(board)["completion"]
        ranks = {}
        for move in moves:
            if perf_counter() >= limit:
                break
            child = self.children(board, move, side)
            ranks[move] = attacker_move_priority(board, move, child,
                                                 escapes_before=escapes_before,
                                                 completion_before=completion_before)
        self.root_strategy_ranks = ranks
        self.stats["attacker_ordering_moves"] = len(ranks)
        self.stats["attacker_ordering_seconds"] = round(perf_counter() - start, 6)
        return ranks

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

        strategic = {}
        if target and side == "A" and getattr(self.options, "attacker_ordering", False):
            strategic = self._compute_root_strategy(board, side, moves)

        def priority(move):
            (row, col), (r, c) = move
            # Tie-break, never a score rule: among equally scored root moves the ones
            # that would repeat a position immediately are searched last. The strategic
            # tuple (V7 E1) sits below the PV/TT hint and above killer/history.
            return (target and move in root_preferred,
                    move not in draw_moves,
                    move == hint,
                    board[row][col] == "K" and (r in (0, size - 1) or c in (0, size - 1)),
                    strategic.get(move, (0, 0, 0, 0, 0, 0, 0.0, 0)),
                    move == killer,
                    history_scores.get((side, move), 0))

        return sorted(moves, key=priority, reverse=True)

    def visit(self, board, side, depth, alpha, beta, history, ply=0, moves=None):
        self.check_time()
        self.stats["nodes"] += 1
        if self.node_budget and self.stats["nodes"] > self.node_budget:
            raise SearchTimeout()
        key = get_state_key(board, side)
        terminal = check_winner(board, side)
        if terminal is None and key in history:
            self.repetition_hits += 1
            return 0.0, ()
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

        context = frozenset(history) if self.options.tt_capacity else None
        cached = self.table.probe(key, depth, alpha, beta, ply, context=context)
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
            if ply == 0 and self.options.deepen_ties and self.side == "A":
                self.root_scores[move] = score  # Fail-low scores can be upper bounds.
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
            self.table.store(key, depth, best, flag, pv[0], ply, context=context)
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
                 fallback_used=False, score=None, pv=[], finish_reason="no_legal_moves", tactical_status="not_checked",
                 full_width_depth=0, candidate_depth=0, tie_research="not_started",
                 tie_changed_move=False, capture_proof="not_started")
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
    if side == "A" and options.capture_proof:
        now = perf_counter()
        budget = min(1000, options.node_budget//10) if options.node_budget else 1000
        proof = prove_capture(board, history, deadline=min(deadline,now+min(.1,max(0,deadline-now)*.1)),
                              max_nodes=budget,moves=moves)
        stats.update(capture_proof=proof.status,capture_proof_nodes=proof.nodes,nodes=proof.nodes)
        if proof.status == "WIN":
            stats.update(score=WIN_SCORE-len(proof.line),pv=proof.line,finish_reason="capture_proof")
            return proof.line[0]
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
    completed_root_scores = {}
    tie_enabled = side == "A" and options.deepen_ties
    primary_deadline, primary_nodes = search.deadline, search.node_budget
    def reserve_for_candidates():
        # Only reserve after a complete depth 3 and a viable near-score candidate.
        if not tie_enabled or stats["full_width_depth"] != 3 or abs(stats["score"]) >= MATE_BOUND:
            return
        if not any(move != best and score >= stats["score"]-.5
                   for move,score in completed_root_scores.items()):
            return
        now = perf_counter()
        if primary_nodes:
            search.node_budget = max(stats["nodes"], primary_nodes - primary_nodes//6)
        else:
            search.deadline = max(now,min(deadline,deadline-min(.15,max(0,deadline-now)/6)))


    for depth in range(1, options.max_depth + 1):
        if perf_counter() >= deadline:
            stats.update(timed_out=True, fallback_used=True, finish_reason="search_deadline")
            break
        if soft_deadline is not None and perf_counter() >= soft_deadline:
            stats.update(fallback_used=True, finish_reason="soft_deadline")
            break
        try:
            search.root_scores.clear()
            score, pv = search.visit(board, side, depth, -inf, inf, history, moves=moves)
        except SearchTimeout:
            stats.update(timed_out=True, fallback_used=True, finish_reason="search_deadline")
            break
        if not pv:
            stats["finish_reason"] = "terminal_position"
            return None
        best = pv[0]
        completed_root_scores = search.root_scores.copy()
        stats.update(completed_depth=depth, full_width_depth=depth, score=score, pv=pv)
        reserve_for_candidates()
        if abs(score) >= MATE_BOUND:
            stats["finish_reason"] = "proven_terminal"
            break
    search.deadline, search.node_budget = primary_deadline, primary_nodes
    if (tie_enabled and stats["full_width_depth"] >= 3
            and abs(stats["score"]) < MATE_BOUND and len(completed_root_scores)>1):
        ranked = sorted((move for move in completed_root_scores if move != best
                         and completed_root_scores[move] >= stats["score"]-.5),
                        key=completed_root_scores.get,reverse=True)
        candidates = [best,*ranked[:3]]
        if len(candidates)>1:
            ancestors = (*history,get_state_key(board,side))
            # Use full windows at one common depth. A partial round cannot change the move.
            stats["tie_research"] = "started"
            original = best
            first = stats["full_width_depth"] + 1
            depths = range(first, 7 if len(moves)<=12 else 6)
            for depth in depths:
                results = []
                try:
                    for move in candidates:
                        search.check_time()
                        child = search.children(board,move,side)
                        score, tail = search.visit(child,"D",depth-1,-inf,inf,ancestors,ply=1)
                        results.append((score,(move,*tail)))
                except SearchTimeout:
                    stats["tie_research"] = "incomplete"
                    break
                score,pv = max(results,key=lambda item:item[0])
                best = pv[0]
                candidates = [best,*[move for move in candidates if move != best]]
                stats.update(candidate_depth=depth,score=score,pv=pv,tie_research="completed",
                             tie_changed_move=best!=original)
    return best
