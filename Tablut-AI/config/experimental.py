"""Opt-in search settings. The course bot uses config/settings.py."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchOptions:
    max_depth: int = 4
    tt_capacity: int = 20_000
    order_moves: bool = True

    def __post_init__(self):
        if self.max_depth < 1 or self.tt_capacity < 0:
            raise ValueError("Search depth must be positive and hint capacity nonnegative")
