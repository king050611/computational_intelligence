"""Shared search options for the official adapter and experiments."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchOptions:
    max_depth: int = 4
    tt_capacity: int = 20_000
    order_moves: bool = True
    node_budget: int = 0

    def __post_init__(self):
        if self.max_depth < 1 or self.tt_capacity < 0:
            raise ValueError("Search depth must be positive and hint capacity nonnegative")
        if type(self.node_budget) is not int or self.node_budget < 0:
            raise ValueError("Node budget must be a nonnegative integer")


STRATEGIES = ("enhanced", "enhanced_dynamic", "evolutionary_dynamic")
TEST_STRATEGIES = ("random",)
AVAILABLE_STRATEGIES = STRATEGIES + TEST_STRATEGIES
