"""Member A: implement simultaneous captures and castle/king exceptions."""
from src.core.state import Board, Position


def resolve_captures(board: Board, destination: Position) -> Board:
    """Input is the board AFTER movement; return a new board after captures."""
    raise NotImplementedError("TODO A: capture rules and regression tests")


def is_king_captured(board: Board, destination: Position) -> bool:
    raise NotImplementedError("TODO A: king capture rules")
