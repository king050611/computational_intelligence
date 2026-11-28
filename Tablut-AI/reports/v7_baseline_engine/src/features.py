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
from src.game import get_piece_moves

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
    best = 9
    for dr, dc in DIRECTIONS:
        row, col, distance = r + dr, c + dc, 0
        clear = True
        while 0 <= row < 9 and 0 <= col < 9:
            if board[row][col] in "ADK":
                clear = False
                break
            distance += 1
            row += dr
            col += dc
        if clear and 0 < distance < best:
            best = distance
    return 0.0 if best == 9 else best / 8


def immediate_king_threat(board, king):
    """1.0 when the king can be captured by one axial attacker move.

    Exact enough for evaluation and cheap: for each side of the king the opposite
    square must already hold an attacker (the support), the adjacent square must be
    empty, and the attacker two squares away must be able to slide in. Diagonal
    approaches from a perpendicular ray are not counted, which keeps this at O(1)
    lookups per side; a missed threat is still seen by the search one ply deeper.
    """
    r, c = king
    near_castle = abs(r - 4) + abs(c - 4) <= 1
    for dr, dc in DIRECTIONS:
        support_r, support_c = r - dr, c - dc
        mover_r, mover_c = r + dr, c + dc
        far_r, far_c = r + 2*dr, c + 2*dc
        if not (0 <= mover_r < 9 and 0 <= mover_c < 9):
            continue
        if board[mover_r][mover_c] != ".":
            continue
        if not (0 <= support_r < 9 and 0 <= support_c < 9):
            continue
        if near_castle:
            if all(0 <= y < 9 and 0 <= x < 9 and board[y][x] in "AX"
                   for y, x in ((r + dy, c + dx) for dy, dx in DIRECTIONS)):
                return 1.0
        elif board[support_r][support_c] == "A":
            if 0 <= far_r < 9 and 0 <= far_c < 9 and board[far_r][far_c] == "A":
                return 1.0
    return 0.0


def extract_features(board):
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
            king_escape_distance(board, king), immediate_king_threat(board, king))
