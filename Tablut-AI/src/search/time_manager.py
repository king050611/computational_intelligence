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
