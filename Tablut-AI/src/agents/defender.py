"""Deterministic legal-move baseline; no tactical intelligence yet."""
from src.core.move_generator import get_legal_moves
from src.core.state import GameState


def choose_defender_move(board):
    moves = get_legal_moves(GameState(board, "D"))
    return moves[0] if moves else None
