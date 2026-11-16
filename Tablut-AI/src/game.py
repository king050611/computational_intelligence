"""Standalone rules. Board is immutable; coordinates are (row, column)."""
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


def get_legal_moves(board: Board, player: str) -> list[Move]:
    if player not in ("A", "D"):
        raise ValueError("Player must be A or D")
    pieces = "A" if player == "A" else "DK"
    moves = []
    for r, row in enumerate(board):
        for c, piece in enumerate(row):
            if piece not in pieces:
                continue
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


def apply_move(board, move, player):
    """Validate and simulate a move; resolve all captures on one snapshot."""
    if move not in get_legal_moves(board, player):
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
            near_castle = abs(ar-4) + abs(ac-4) <= 1
            take = (all(result[ar+dy][ac+dx] in "AX" for dy, dx in DIRECTIONS)
                    if near_castle else support == "A")
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
    if get_state_key(board, player) in history or not get_legal_moves(board, player):
        return "DRAW"
    return None
