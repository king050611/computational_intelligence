"""Eight bounded, defender-perspective features for evolutionary evaluation.

V5 adds two structural signals that the six-feature model could not express:

* ``king_escape_distance`` - how far the king still is from an edge along its best
  *clear* ray, not a geometric distance that ignores blockers;
* ``immediate_king_threat`` - whether an attacker could capture the king with its next
  move, which is the sharpest short-horizon danger signal.

Both are zero-initialised in ``BASE_WEIGHTS``, so an untrained model behaves exactly
like the six-feature baseline.
"""
from config.settings import DIRECTIONS
from src.game import get_piece_moves, king_capture_supported

FEATURE_NAMES = ("king_pressure", "escape_routes", "weighted_material", "edge_distance",
                 "king_mobility", "escape_blockade", "king_escape_distance", "immediate_king_threat")


def basic_features(board):
    king = next(((r,c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)
    material = sum(row.count("A") - 2*row.count("D") for row in board)
    if king is None:
        return 4, 0, material
    r,c = king
    pressure = sum(0 <= r+dr < 9 and 0 <= c+dc < 9 and board[r+dr][c+dc] == "A" for dr,dc in DIRECTIONS)
    # Only the king's own moves are generated: the defender's other pieces cannot escape.
    escapes = sum(0 in end or 8 in end for end in (end for _,end in get_piece_moves(board,king,"D")))
    return pressure, escapes, material


def king_escape_distance(board, king):
    """Steps from the king to the nearest edge along a fully clear ray, /8."""
    r, c = king
    if r in (0, 8) or c in (0, 8):
        return 0.0
    distances = [abs(row-r) + abs(col-c)
                 for _, (row, col) in get_piece_moves(board, king, "D")
                 if row in (0, 8) or col in (0, 8)]
    return min(distances, default=8) / 8


def immediate_king_threat(board, king):
    """Detect a legal attacker landing that captures the king in one move."""
    row, col = king
    for dr, dc in DIRECTIONS:
        target = (row + dr, col + dc)
        nr, nc = target
        if not (0 <= nr < 9 and 0 <= nc < 9) or board[nr][nc] != ".":
            continue
        if not king_capture_supported(board, king, target):
            continue
        # Reverse the legal slide from its destination. The first piece on each
        # ray is the only possible source, and it cannot double as support.
        for dy, dx in DIRECTIONS:
            sr, sc = nr + dy, nc + dx
            while 0 <= sr < 9 and 0 <= sc < 9:
                piece = board[sr][sc]
                if piece not in ".X":
                    if piece == "A" and king_capture_supported(board, king, target, (sr, sc)):
                        return 1.0
                    break
                sr, sc = sr + dy, sc + dx
    return 0.0


def extract_features(board, *, escape_distance=True, king_threat=True):
    king = next(((r,c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)
    material = sum(row.count("A") - 2*row.count("D") for row in board)
    if king is None:
        return 1.0, 0.0, material/16, 1.0, 0.0, 1.0, 1.0, 0.0
    r,c = king
    destinations = [end for _, end in get_piece_moves(board,king,"D")]
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
    return (pressure/4, escapes/4, material/16, min(r,c,8-r,8-c)/4, len(destinations)/16, blockade/4,
            (min((abs(y-r)+abs(x-c) for y,x in destinations if y in (0,8) or x in (0,8)), default=8) / 8
             if escape_distance and r not in (0,8) and c not in (0,8) else 0.0),
            immediate_king_threat(board, king) if king_threat else 0.0)
