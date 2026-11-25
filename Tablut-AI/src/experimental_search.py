"""Dispatch opt-in strategies without modifying the Assessment search."""
from src.enhanced_search import choose_enhanced

EXPERIMENTAL_STRATEGIES = ("enhanced", "enhanced_dynamic")


def choose_experimental_move(board, side, *, strategy, deadline, history=(),
                             evaluator=None, rng=None, stats=None, options=None,
                             soft_deadline=None, moves=None):
    if strategy not in EXPERIMENTAL_STRATEGIES:
        raise ValueError(f"Unknown experimental strategy: {strategy}")
    if stats is not None:
        stats["strategy"] = strategy
    return choose_enhanced(board, side, deadline=deadline, soft_deadline=soft_deadline,
                           history=history, evaluator=evaluator, stats=stats,
                           options=options, moves=moves)
