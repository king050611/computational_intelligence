"""Full-width iterative Alpha-Beta. Hints never cache scores."""
from functools import lru_cache
from math import inf
from time import perf_counter

from config.experimental import SearchOptions
from config.settings import DIRECTIONS
from src.evaluation import evaluate_attacker, evaluate_defender
from src.game import apply_move, check_winner, get_legal_moves, get_state_key
from src.search import SearchTimeout, WIN_SCORE
from src.tactics import opponent
from src.transposition import MoveHints


def evaluate(board, side):
    return (evaluate_attacker if side == "A" else evaluate_defender)(board)


class EnhancedSearch:
    """One decision's state, including bounded move ordering hints."""

    def __init__(self, side, deadline, evaluator, options, stats):
        self.side = side
        self.deadline = deadline
        self.evaluator = evaluator
        self.options = options
        self.stats = stats
        self.hints = MoveHints(options.tt_capacity)
        self.children = lru_cache(maxsize=4096)(apply_move)
        self.killers = {}
        self.history_scores = {}

    def check_time(self):
        if perf_counter() >= self.deadline:
            raise SearchTimeout()

    def order(self, board, side, moves, ply):
        if not self.options.order_moves:
            return moves
        hint = self.hints.get(get_state_key(board, side))
        if hint in moves:
            self.stats["tt_hint_hits"] += 1
        killer = self.killers.get(ply)
        enemies = "DK" if side == "A" else "A"
        size = len(board)

        def priority(move):
            (row, col), (r, c) = move
            escape = board[row][col] == "K" and (r in (0, size - 1) or c in (0, size - 1))
            # Cheap capture potential. The rule engine still decides captures.
            contact = any(0 <= r + dr < size and 0 <= c + dc < size
                          and board[r + dr][c + dc] in enemies for dr, dc in DIRECTIONS)
            return escape, move == hint, contact, move == killer, self.history_scores.get((side, move), 0)

        return sorted(moves, key=priority, reverse=True)

    def visit(self, board, side, depth, alpha, beta, history, ply=0, moves=None):
        self.check_time()
        self.stats["nodes"] += 1
        terminal = check_winner(board, side, history)
        self.check_time()
        if terminal is not None:
            score = 0.0 if terminal == "DRAW" else WIN_SCORE if terminal == self.side else -WIN_SCORE
            return score, ()
        if depth == 0:
            score = self.evaluator(board, self.side)
            self.check_time()
            return score, ()

        key = get_state_key(board, side)
        ancestors = history + (key,)
        maximizing = side == self.side
        best, pv = (-inf if maximizing else inf), ()
        if moves is None:
            moves = get_legal_moves(board, side)
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
                    if sum(row.count("A") + row.count("D") + row.count("K") for row in board) == sum(
                            row.count("A") + row.count("D") + row.count("K") for row in child):
                        self.killers[ply] = move
                    self.history_scores[side, move] = self.history_scores.get((side, move), 0) + depth ** 2
                break
        self.check_time()
        if pv and self.options.order_moves:
            self.hints.put(key, depth, pv[0])
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
                 fallback_used=False, score=None, pv=[], finish_reason="no_legal_moves")
    if not moves:
        return None
    best = moves[0]
    search = EnhancedSearch(side, deadline, evaluator or evaluate, options, stats)
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
        if abs(score) == WIN_SCORE:
            stats["finish_reason"] = "proven_terminal"
            break
    return best
