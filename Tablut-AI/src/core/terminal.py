"""Member A: terminal detection. History contains PRIOR state keys only."""
from typing import Iterable, Optional
from src.core.state import GameState, StateKey


def get_game_result(state: GameState, history: Iterable[StateKey] = ()) -> Optional[str]:
    """Return A, D, DRAW, or None (ongoing); include turn in repetition key."""
    raise NotImplementedError("TODO A: wins, no moves, repeated position")
