"""Analysis-only blockade and escape indicators (V7 Phase 1, not used by the search).

These functions deliberately live outside the evaluation function: Phase 1 asks whether
these quantities actually separate attacker wins from attacker losses *before* any of
them is promoted to an evaluation feature.

Nothing here changes game rules or search behaviour.
"""
from config.settings import DIRECTIONS
from src.game import apply_move, check_winner, get_legal_moves, get_piece_moves

EDGE = {0, 8}


def _ray_dests(board, position):
    """Squares reachable from ``position`` in one sliding step (castle passable)."""
    out = []
    r, c = position
    for dr, dc in DIRECTIONS:
        row, col = r, c
        while True:
            row += dr
            col += dc
            if not (0 <= row < 9 and 0 <= col < 9):
                break
            cell = board[row][col]
            if cell in "ADK":
                break
            if cell == ".":
                out.append((row, col))
    return out


def king_square(board):
    return next(((r, c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)


def escape_reachability(board, depth=2):
    """Distinct edge squares the king could reach in at most ``depth`` own moves."""
    king = king_square(board)
    if king is None:
        return 0
    seen, frontier = {king}, {king}
    for _ in range(max(1, depth)):
        nxt = set()
        for position in frontier:
            for dest in _ray_dests(board, position):
                if dest not in seen:
                    nxt.add(dest)
        seen |= nxt
        frontier = nxt
    return sum(1 for r, c in seen if r in EDGE or c in EDGE)


def king_moves(board):
    king = king_square(board)
    return [] if king is None else [end for _, end in get_piece_moves(board, king, "D")]


def immediate_escape(board):
    return sum(1 for r, c in king_moves(board) if r in EDGE or c in EDGE)


def adjacent_attackers(board):
    king = king_square(board)
    if king is None:
        return 0
    r, c = king
    return sum(0 <= r + dr < 9 and 0 <= c + dc < 9 and board[r + dr][c + dc] == "A"
               for dr, dc in DIRECTIONS)


def supported_attackers(board):
    """Adjacent attackers that have at least one orthogonal attacker neighbour."""
    king = king_square(board)
    if king is None:
        return 0
    r, c = king
    count = 0
    for dr, dc in DIRECTIONS:
        ar, ac = r + dr, c + dc
        if not (0 <= ar < 9 and 0 <= ac < 9) or board[ar][ac] != "A":
            continue
        if any(0 <= ar + dy < 9 and 0 <= ac + dx < 9 and board[ar + dy][ac + dx] == "A"
               for dy, dx in DIRECTIONS):
            count += 1
    return count


def attacking_moves(board):
    """Legal attacker moves, split into immediate mates and defender captures."""
    mates, captures = [], []
    for move in get_legal_moves(board, "A"):
        child = apply_move(board, move, "A")
        if check_winner(child, "D") == "A":
            mates.append(move)
            continue
        if sum(row.count("D") for row in child) < sum(row.count("D") for row in board):
            captures.append(move)
    return mates, captures


def snapshot(board):
    """All indicators for one position, from the attacker's point of view."""
    mates, captures = attacking_moves(board)
    return dict(king_adjacent_attackers=adjacent_attackers(board),
                supported_attackers=supported_attackers(board),
                king_moves=len(king_moves(board)),
                immediate_escape=immediate_escape(board),
                escape_reach_2=escape_reachability(board, 2),
                attacker_mates=len(mates),
                attackercaptures=len(captures),
                defenders=sum(row.count("D") for row in board))
