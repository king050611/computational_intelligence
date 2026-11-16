"""Deterministic legal-move baseline; replace with search later."""
from src.core.move_generator import get_legal_moves
from src.core.state import GameState


def choose_attacker_move(board):
    moves = get_legal_moves(GameState(board, "A"))
    return moves[0] if moves else None
