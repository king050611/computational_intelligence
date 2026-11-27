"""Standalone rules. Board is immutable; coordinates are (row, column).

V4 keeps the rules byte-for-byte equivalent to the official referee but adds the
incremental primitives the engine needs: single-piece move generation, O(path)
legality checks and an O(81) "has any move" scan. They exist so the search stops
paying for a full move generation at every node.
"""
from typing import Tuple, Sequence
from config.settings import BOARD_SIZE, CASTLE, INITIAL_BOARD, DIRECTIONS
Position = Tuple[int, int]
Move = Tuple[Position, Position]
Board = Tuple[Tuple[str, ...], ...]

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


def initial_board() -> Board:
    return parse_board(INITIAL_BOARD)


def get_state_key(board, player):
    return tuple(map(tuple, board)), player


def _piece_moves(board: Board, r: int, c: int) -> list[Move]:
    """Every destination of the piece on (r, c); the castle is passable, not a target."""
    moves = []
    for dr, dc in DIRECTIONS:
        nr, nc = r + dr, c + dc
        while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
            cell = board[nr][nc]
            if cell not in (".", "X"):
                break
            if cell == ".":
                moves.append(((r, c), (nr, nc)))
            nr, nc = nr + dr, nc + dc
    return moves


def get_piece_moves(board: Board, position: Position, player: str) -> list[Move]:
    """Moves of the single piece at ``position``; empty when that piece is not the player's."""
    if player not in ("A", "D"):
        raise ValueError("Player must be A or D")
    r, c = position
    if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
        return []
    pieces = "A" if player == "A" else "DK"
    if board[r][c] not in pieces:
        return []
    return _piece_moves(board, r, c)


def has_any_move(board: Board, player: str) -> bool:
    """True when at least one legal move exists; never builds the move list."""
    if player not in ("A", "D"):
        raise ValueError("Player must be A or D")
    pieces = "A" if player == "A" else "DK"
    for r, row in enumerate(board):
        for c, piece in enumerate(row):
            if piece not in pieces:
                continue
            for dr, dc in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE):
                    continue
                cell = board[nr][nc]
                if cell == ".":
                    return True
                if cell == "X":
                    br, bc = nr + dr, nc + dc
                    if 0 <= br < BOARD_SIZE and 0 <= bc < BOARD_SIZE and board[br][bc] == ".":
                        return True
    return False


def get_legal_moves(board: Board, player: str) -> list[Move]:
    if player not in ("A", "D"):
        raise ValueError("Player must be A or D")
    pieces = "A" if player == "A" else "DK"
    moves = []
    for r, row in enumerate(board):
        for c, piece in enumerate(row):
            if piece in pieces:
                moves.extend(_piece_moves(board, r, c))
    return moves


def is_legal_move(board: Board, move, player: str) -> bool:
    """O(path) legality check equivalent to ``move in get_legal_moves(board, player)``."""
    if player not in ("A", "D"):
        raise ValueError("Player must be A or D")
    try:
        (r, c), (nr, nc) = move
    except (TypeError, ValueError):
        return False
    if any(type(v) is not int for v in (r, c, nr, nc)):
        return False
    if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE
            and 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE):
        return False
    pieces = "A" if player == "A" else "DK"
    if board[r][c] not in pieces or board[nr][nc] != ".":
        return False
    if r == nr:
        step = 1 if nc > c else -1
        return all(board[r][cc] in (".", "X") for cc in range(c + step, nc, step))
    if c == nc:
        step = 1 if nr > r else -1
        return all(board[rr][c] in (".", "X") for rr in range(r + step, nr, step))
    return False


def king_capture_supported(board, king, destination, origin=None):
    """Apply the king capture rule to an attacker landing next to the king."""
    row, col = king
    dr, dc = destination[0] - row, destination[1] - col
    sr, sc = row - dr, col - dc
    if not (0 <= sr < BOARD_SIZE and 0 <= sc < BOARD_SIZE):
        return False

    def cell(r, c):
        if (r, c) == destination:
            return "A"
        return "." if (r, c) == origin else board[r][c]

    if abs(row - 4) + abs(col - 4) <= 1:
        return all(cell(row + dy, col + dx) in "AX" for dy, dx in DIRECTIONS)
    return cell(sr, sc) == "A"


def apply_move(board, move, player):
    """Validate and simulate a move; resolve all captures on one snapshot."""
    if not is_legal_move(board, move, player):
        raise ValueError("Illegal move")
    (r, c), (nr, nc) = move
    result = [list(row) for row in board]
    piece = result[r][c]
    result[r][c] = "X" if (r, c) == CASTLE else "."
    result[nr][nc] = piece
    captured = []
    for dr, dc in DIRECTIONS:
        ar, ac = nr + dr, nc + dc
        br, bc = nr + 2*dr, nc + 2*dc
        if not (0 <= br < 9 and 0 <= bc < 9):
            continue
        victim, support = result[ar][ac], result[br][bc]
        take = False
        if piece in "DK" and victim == "A":
            take = support in "DKX"
        elif piece == "A" and victim == "D":
            take = support in "AX"
            if support == "K" and (br, bc) == CASTLE:
                take = sum(result[4+dy][4+dx] == "A" for dy, dx in DIRECTIONS) == 3
        elif piece == "A" and victim == "K":
            take = king_capture_supported(result, (ar, ac), (nr, nc))
        if take:
            captured.append((ar, ac))
    for ar, ac in captured:
        result[ar][ac] = "X" if (ar, ac) == CASTLE else "."
    return tuple(map(tuple, result))


def check_winner(board, player, history=()):
    """A/D/DRAW/None. History contains previous (board, player) keys only."""
    king = next(((r,c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)
    if king is None:
        return "A"
    if 0 in king or 8 in king or sum(row.count("A") for row in board) < 2:
        return "D"
    if get_state_key(board, player) in history or not has_any_move(board, player):
        return "DRAW"
    return None
