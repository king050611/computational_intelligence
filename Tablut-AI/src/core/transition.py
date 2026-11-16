"""Member A: copy, move, restore X, resolve captures, switch turn."""
from src.core.state import GameState, Move


def apply_move(state: GameState, move: Move) -> GameState:
    """Reject illegal moves with ValueError; never mutate the original state."""
    raise NotImplementedError("TODO A: full transition including captures")
