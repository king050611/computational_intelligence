"""Member B: shared search; evaluator score is from root player's view."""
from typing import Callable, Optional
from src.core.state import GameState, Move


def alpha_beta_search(state: GameState, depth: int,
                      evaluate: Callable[[GameState], float],
                      deadline: float) -> Optional[Move]:
    """deadline uses time.perf_counter(); return None when no legal moves."""
    raise NotImplementedError("TODO B: minimax, alpha-beta and legal fallback")


def minimax(state: GameState, depth: int, evaluate: Callable[[GameState], float],
            deadline: float) -> Optional[Move]:
    raise NotImplementedError("TODO B: unpruned reference search")
