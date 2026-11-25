"""Separate soft and hard deadlines for the experimental strategy."""
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
