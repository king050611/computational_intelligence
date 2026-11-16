"""Cumulative clock helper; create once per player per game."""
from time import perf_counter
from config.settings import GAME_TIME_LIMIT, TIME_SAFETY_MARGIN


class TimeManager:
    def __init__(self, limit=GAME_TIME_LIMIT, margin=TIME_SAFETY_MARGIN):
        if not 0 <= margin < limit:
            raise ValueError("Require 0 <= margin < limit")
        self.limit, self.margin, self.spent = limit, margin, 0.0

    def allocate_time(self, expected_moves=30):
        if expected_moves <= 0:
            raise ValueError("expected_moves must be positive")
        return max(0.0, self.limit - self.margin - self.spent) / expected_moves

    def deadline(self, expected_moves=30):
        return perf_counter() + self.allocate_time(expected_moves)

    def record_elapsed(self, elapsed):
        if elapsed < 0:
            raise ValueError("elapsed must not be negative")
        self.spent += elapsed


def time_exceeded(deadline):
    return perf_counter() >= deadline


from config.settings import (SEARCH_DEPTH, MAX_SEARCH_DEPTH, ENABLE_ALPHA_BETA,
                             ENABLE_MOVE_ORDERING, DEEP_SEARCH_MIN_SECONDS,
                             DEEP_SEARCH_MAX_BRANCHES)
from src.game import get_legal_moves, apply_move, check_winner, get_state_key
from src.evaluation import evaluate_attacker, evaluate_defender

STRATEGIES = ("first", "random", "greedy", "minimax", "adaptive")
WIN_SCORE = 1_000_000_000.0


class SearchTimeout(Exception):
    """Internal signal: discard the unfinished iteration."""


def _check_time(deadline):
    if time_exceeded(deadline):
        raise SearchTimeout()


def _score(board, current, root, path):
    result = check_winner(board, current, path)
    if result is not None:
        return (0.0 if result == "DRAW" else WIN_SCORE if result == root else -WIN_SCORE)
    return None


def _evaluate(board, root):
    return (evaluate_attacker if root == "A" else evaluate_defender)(board)


def alpha_beta(board, current_player, root_player, depth, alpha, beta, deadline,
               path=(), *, prune=ENABLE_ALPHA_BETA, stats=None):
    """Fixed root perspective; path contains ancestors including their turns."""
    _check_time(deadline)
    if stats is not None:
        stats["nodes"] = stats.get("nodes", 0) + 1
    terminal = _score(board, current_player, root_player, path)
    if terminal is not None:
        return terminal
    if depth <= 0:
        return _evaluate(board, root_player)
    maximizing = current_player == root_player
    value = -float("inf") if maximizing else float("inf")
    next_player = "D" if current_player == "A" else "A"
    ancestors = path + (get_state_key(board, current_player),)
    for move in get_legal_moves(board, current_player):
        _check_time(deadline)
        child = apply_move(board, move, current_player)
        score = alpha_beta(child, next_player, root_player, depth-1, alpha, beta,
                           deadline, ancestors, prune=prune, stats=stats)
        if maximizing:
            value, alpha = max(value, score), max(alpha, score)
        else:
            value, beta = min(value, score), min(beta, score)
        if prune and alpha >= beta:
            break
    return value


def is_urgent(board):
    """An open king escape or two adjacent attackers marks a tactical position."""
    king = next(((r,c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)
    if king is None:
        return False
    r,c = king
    pressure = sum(0 <= r+dr < 9 and 0 <= c+dc < 9 and board[r+dr][c+dc] == "A"
                   for dr,dc in ((-1,0),(1,0),(0,-1),(0,1)))
    return pressure >= 2 or any(start == king and (0 in end or 8 in end)
                                for start,end in get_legal_moves(board,"D"))


def choose_move(board, player, deadline=float("inf"), strategy="adaptive", rng=None, stats=None):
    """Depth 1 greedy, then complete depth 2/3 iterations; always keep a fallback."""
    if strategy not in STRATEGIES:
        raise ValueError("Unknown strategy")
    moves = get_legal_moves(board, player)
    if stats is not None:
        stats.update(completed_depth=0, nodes=0, timed_out=False, target_depth=0)
    if not moves:
        return None
    if strategy == "first":
        return moves[0]
    if strategy == "random":
        if rng is None:
            raise ValueError("random strategy requires a seeded RNG")
        return rng.choice(moves)
    best, best_score, ranked = moves[0], -float("inf"), []
    next_player = "D" if player == "A" else "A"
    path = (get_state_key(board, player),)
    try:
        # Complete a greedy pass first; this also detects immediate wins.
        for move in moves:
            _check_time(deadline)
            child = apply_move(board, move, player)
            score = _score(child, next_player, player, path)
            if score is None:
                score = _evaluate(child, player)
            ranked.append((score, move, child))
            if score > best_score:
                best, best_score = move, score
            if score == WIN_SCORE:
                if stats is not None:
                    stats["completed_depth"] = 1
                return move
        if stats is not None:
            stats["completed_depth"] = 1
        if strategy == "greedy":
            return best
        target = SEARCH_DEPTH
        if (strategy == "adaptive" and is_urgent(board)
                and len(moves) <= DEEP_SEARCH_MAX_BRANCHES
                and deadline - perf_counter() >= DEEP_SEARCH_MIN_SECONDS):
            target = MAX_SEARCH_DEPTH
        if stats is not None:
            stats["target_depth"] = target
        if ENABLE_MOVE_ORDERING:
            ranked.sort(key=lambda item: item[0], reverse=True)
        for depth in range(2, target+1):
            iteration_best, value, alpha = best, -float("inf"), -float("inf")
            for _, move, child in ranked:
                _check_time(deadline)
                score = alpha_beta(child, next_player, player, depth-1,
                                   alpha, float("inf"), deadline, path, stats=stats)
                if score > value:
                    iteration_best, value = move, score
                alpha = max(alpha, score)
            # Only publish a fully finished iteration.
            best = iteration_best
            if stats is not None:
                stats["completed_depth"] = depth
            if abs(value) == WIN_SCORE:
                break
    except SearchTimeout:
        if stats is not None:
            stats["timed_out"] = True
    return best
