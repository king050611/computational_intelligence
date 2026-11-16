"""Three features per side; higher scores favor the named side."""
from config.settings import ATTACKER_WEIGHTS, DEFENDER_WEIGHTS, DIRECTIONS
from src.game import get_legal_moves


def _features(board):
    king = next(((r,c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)
    if king is None:
        return 4, 0, sum(row.count("A") for row in board)
    r, c = king
    pressure = sum(0 <= r+dr < 9 and 0 <= c+dc < 9 and board[r+dr][c+dc] == "A"
                   for dr, dc in DIRECTIONS)
    escapes = sum(start == king and (0 in end or 8 in end)
                  for start, end in get_legal_moves(board, "D"))
    material = sum(row.count("A") - 2*row.count("D") for row in board)
    return pressure, escapes, material


def evaluate_attacker(board):
    pressure, escapes, material = _features(board)
    w = ATTACKER_WEIGHTS
    return w["king_pressure"]*pressure + w["king_escape_risk"]*escapes + w["piece_advantage"]*material


def evaluate_defender(board):
    pressure, escapes, material = _features(board)
    w = DEFENDER_WEIGHTS
    return -w["king_safety"]*pressure + w["escape_routes"]*escapes - w["piece_advantage"]*material
