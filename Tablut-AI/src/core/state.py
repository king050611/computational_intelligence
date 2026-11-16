"""Immutable internal representation, independent of the teacher framework."""
from dataclasses import dataclass
from typing import Tuple, Sequence
from config.rules import BOARD_SIZE, CASTLE, INITIAL_BOARD
Position = Tuple[int, int]
Move = Tuple[Position, Position]
Board = Tuple[Tuple[str, ...], ...]
StateKey = Tuple[Board, str]


def parse_board(board: Sequence[Sequence[str]]) -> Board:
    if len(board) != BOARD_SIZE or any(len(row) != BOARD_SIZE for row in board):
        raise ValueError("Expected a 9 x 9 board")
    result = tuple(tuple(row) for row in board)
    if any(cell not in ".XADK" for row in result for cell in row):
        raise ValueError("Unknown board symbol")
    for r, row in enumerate(result):
        for c, cell in enumerate(row):
            if cell == "X" and (r, c) != CASTLE:
                raise ValueError("X must mark the central castle")
    if result[4][4] not in ("X", "K"):
        raise ValueError("Central castle must contain K or X")
    return result


@dataclass(frozen=True)
class GameState:
    board: Board
    player: str = "A"

    def __post_init__(self):
        object.__setattr__(self, "board", parse_board(self.board))
        if self.player not in ("A", "D"):
            raise ValueError("Player must be A or D (including the king)")


def initial_state() -> GameState:
    return GameState(parse_board(INITIAL_BOARD))


def get_state_key(state: GameState) -> StateKey:
    return state.board, state.player
