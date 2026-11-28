"""Cumulative static and dynamic clocks shared by all strategy adapters."""
from time import perf_counter
from config.settings import GAME_TIME_LIMIT, TIME_SAFETY_MARGIN


class AdaptiveTimeManager:
    def __init__(self):
        self.spent = 0.0
        self.turns = 0

    def deadlines(self, start, complexity=1.0):
        available = max(0.0, GAME_TIME_LIMIT - TIME_SAFETY_MARGIN - self.spent)
        remaining = max(8, 30 - self.turns // 2)
        allocation = min(available / remaining * complexity, available * 0.20, 4.0)
        return start + allocation * 0.80, start + allocation

    def record_elapsed(self, elapsed):
        if elapsed < 0:
            raise ValueError("Elapsed time must be nonnegative")
        self.spent += elapsed
        self.turns += 1


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
