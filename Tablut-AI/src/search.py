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


from src.game import get_legal_moves, apply_move, check_winner
from src.evaluation import evaluate_attacker, evaluate_defender


def choose_move(board, player, deadline=float("inf"), strategy="greedy", rng=None):
    """Legal fallback if budget expires; first/random are experiment baselines."""
    if strategy not in ("greedy", "first", "random"):
        raise ValueError("Unknown strategy")
    moves = get_legal_moves(board, player)
    if not moves:
        return None
    if strategy == "first":
        return moves[0]
    if strategy == "random":
        if rng is None:
            raise ValueError("random strategy requires a seeded RNG")
        return rng.choice(moves)
    evaluate = evaluate_attacker if player == "A" else evaluate_defender
    best, best_score = moves[0], -float("inf")
    for move in moves:
        if time_exceeded(deadline):
            break
        child = apply_move(board, move, player)
        outcome = check_winner(child, "D" if player == "A" else "A")
        score = (float("inf") if outcome == player else
                 -float("inf") if outcome in ("A", "D") else
                 0 if outcome == "DRAW" else evaluate(child))
        if score > best_score:
            best, best_score = move, score
        if outcome == player:
            break
    return best
