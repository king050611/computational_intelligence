"""Six bounded, defender-perspective features for evolutionary evaluation."""
from config.settings import DIRECTIONS
from src.game import get_legal_moves

FEATURE_NAMES = ("king_pressure", "escape_routes", "weighted_material", "edge_distance", "king_mobility", "escape_blockade")

def basic_features(board):
    king = next(((r,c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)
    material = sum(row.count("A") - 2*row.count("D") for row in board)
    if king is None:
        return 4, 0, material
    r,c = king
    pressure = sum(0 <= r+dr < 9 and 0 <= c+dc < 9 and board[r+dr][c+dc] == "A" for dr,dc in DIRECTIONS)
    escapes = sum(start == king and (0 in end or 8 in end) for start,end in get_legal_moves(board,"D"))
    return pressure, escapes, material

def extract_features(board):
    king = next(((r,c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)
    material = sum(row.count("A") - 2*row.count("D") for row in board)
    if king is None:
        return 1.0, 0.0, material/16, 1.0, 0.0, 1.0
    r,c = king
    destinations = [end for start,end in get_legal_moves(board,"D") if start == king]
    pressure = sum(0 <= r+dr < 9 and 0 <= c+dc < 9 and board[r+dr][c+dc] == "A" for dr,dc in DIRECTIONS)
    escapes = sum(0 in end or 8 in end for end in destinations)
    blockade = 0.0
    for dr,dc in DIRECTIONS:
        for distance in range(1,9):
            nr,nc = r+dr*distance,c+dc*distance
            if not (0 <= nr < 9 and 0 <= nc < 9):
                break
            if board[nr][nc] in "ADK":
                if board[nr][nc] == "A":
                    blockade += 1/distance
                break
    return pressure/4, escapes/4, material/16, min(r,c,8-r,8-c)/4, len(destinations)/16, blockade/4
