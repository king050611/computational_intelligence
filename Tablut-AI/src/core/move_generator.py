"""Orthogonal sliding; empty castle can be crossed but not occupied."""
from config.rules import BOARD_SIZE, DIRECTIONS
from src.core.state import GameState, Move


def get_legal_moves(state: GameState) -> list[Move]:
    pieces = "A" if state.player == "A" else "DK"
    moves = []
    for r, row in enumerate(state.board):
        for c, piece in enumerate(row):
            if piece not in pieces:
                continue
            for dr, dc in DIRECTIONS:
                nr, nc = r + dr, c + dc
                while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                    cell = state.board[nr][nc]
                    if cell not in (".", "X"):
                        break
                    if cell == ".":
                        moves.append(((r, c), (nr, nc)))
                    nr, nc = nr + dr, nc + dc
    return moves


def is_legal_move(state: GameState, move: Move) -> bool:
    return move in get_legal_moves(state)
