"""Rule-confirmed one-move threats for diagnostics on bounded budgets."""
from dataclasses import dataclass
from time import perf_counter

from src.game import apply_move, check_winner, get_legal_moves, get_state_key


def opponent(side):
    return "D" if side == "A" else "A"


@dataclass(frozen=True)
class TacticalInfo:
    immediate_wins: tuple
    opponent_threat_now: object
    safe_replies: tuple
    status_complete: bool
    risk_level: str


def analyze(board, side, deadline, history=(), max_nodes=None):
    """Unknown results stay explicit if the scan runs out of time or work."""
    wins, safe, threat = [], [], None
    path = tuple(history) + (get_state_key(board, side),)
    other = opponent(side)
    work = [0]

    def tick():
        work[0] += 1
        if max_nodes is not None and work[0] > max_nodes:
            raise TimeoutError
        if perf_counter() >= deadline:
            raise TimeoutError

    def children(position, turn):
        for move in get_legal_moves(position, turn):
            tick()
            yield move, apply_move(position, move, turn)

    def outcome(child, turn, ancestors):
        result = check_winner(child, turn, ancestors)
        tick()
        return result

    try:
        if perf_counter() >= deadline:
            raise TimeoutError
        for move, child in children(board, side):
            if outcome(child, other, path) == side:
                wins.append(move)
        if wins:
            return TacticalInfo(tuple(wins), None, (), True, "critical")
        # Evaluate the threat from the opponent-to-move version of this board.
        opponent_path = tuple(history) + (get_state_key(board, other),)
        threat = any(outcome(child, side, opponent_path) == other
                     for _, child in children(board, other))
        if threat:
            for move, child in children(board, side):
                result = outcome(child, other, path)
                if result == "DRAW" or (result is None and not any(
                        outcome(reply, side, path + (get_state_key(child, other),)) == other
                        for _, reply in children(child, other))):
                    safe.append(move)
    except TimeoutError:
        return TacticalInfo(tuple(wins), threat, tuple(safe), False, "unknown")
    return TacticalInfo(tuple(wins), threat, tuple(safe), True, "critical" if threat else "normal")


def is_urgent(board):
    """An open king escape or two adjacent attackers marks a tactical position."""
    king = next(((r,c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)
    if king is None:
        return False
    r,c = king
    pressure = sum(0 <= r+dr < 9 and 0 <= c+dc < 9 and board[r+dr][c+dc] == "A"
                   for dr,dc in ((-1,0),(1,0),(0,-1),(0,1)))
    return pressure >= 2 or any(start == king and (0 in end or 8 in end)
                                for start,end in get_legal_moves(board,"D"))


def prioritize(board,side,moves,deadline,history=(),max_nodes=None):
    """Keep every legal move; only proved wins or fully checked defenses lead."""
    info=analyze(board,side,deadline,history,max_nodes)
    preferred=info.immediate_wins or (info.safe_replies if info.status_complete and info.opponent_threat_now else ())
    preferred=set(preferred)
    return sorted(moves,key=lambda move:move in preferred,reverse=True),info

# --- V7 attacker-only strategic ordering (E1) ---------------------------------------
# Everything below is read-only analysis used for move ordering. It never changes the
# rules, never removes a legal move, and every "capture" is confirmed with the rule
# engine rather than inferred from geometry alone.

EDGE = {0, 8}
CASTLE = (4, 4)
NEAR_CASTLE = {(4, 3), (4, 4), (4, 5), (3, 4), (5, 4)}
DIRECTIONS = ((-1, 0), (0, -1), (1, 0), (0, 1))


def king_square(board):
    return next(((r, c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)


def king_region(board):
    king = king_square(board)
    if king is None:
        return "none"
    if king == CASTLE:
        return "castle"
    if king in NEAR_CASTLE:
        return "beside_castle"
    return "field"


def _gap_reachable(board, square):
    """True when some attacker can slide into an empty square (first piece on a ray is A)."""
    r, c = square
    for dr, dc in DIRECTIONS:
        row, col = r + dr, c + dc
        while 0 <= row < 9 and 0 <= col < 9:
            piece = board[row][col]
            if piece == "X":
                row += dr
                col += dc
                continue
            if piece == "A":
                return True
            break
    return False


def _neighbour_squares(king):
    r, c = king
    return [(r + dr, c + dc) for dr, dc in DIRECTIONS if 0 <= r + dr < 9 and 0 <= c + dc < 9]


def structure_state(board):
    """Region-aware capture requirement: completion, gaps and whether each gap is reachable."""
    king = king_square(board)
    state = dict(region="none", required=0, occupied=0, completion=0.0, gaps=[], reachable=[])
    if king is None:
        return state
    region = king_region(board)
    neighbours = _neighbour_squares(king)
    if region in ("castle", "beside_castle"):
        occupied = [sq for sq in neighbours if board[sq[0]][sq[1]] in "AX"]
        required = len(neighbours)
        gaps = [sq for sq in neighbours if sq not in occupied]
        completion = len(occupied) / required if required else 0.0
    else:
        occupied, gaps, completion = [], [], 0.0
        r, c = king
        for dr, dc in DIRECTIONS:
            first, second = (r + dr, c + dc), (r - dr, c - dc)
            if not (0 <= first[0] < 9 and 0 <= first[1] < 9 and 0 <= second[0] < 9 and 0 <= second[1] < 9):
                continue
            values = (board[first[0]][first[1]], board[second[0]][second[1]])
            filled = sum(1 for value in values if value in "AX")
            if "A" in values:
                completion = max(completion, filled / 2)
                if filled == 2:
                    occupied = [first, second]
                    gaps = []
        if completion < 1.0:
            gaps = [sq for sq in neighbours if board[sq[0]][sq[1]] not in "AX"]
        required = 2
    reachable = [sq for sq in gaps if _gap_reachable(board, sq)]
    state.update(region=region, required=required, occupied=len(occupied),
                 completion=completion, gaps=gaps, reachable=reachable)
    return state


def capture_threat_available(board):
    """True when the attacker has a legal way to complete a capture on its next move."""
    state = structure_state(board)
    if state["region"] == "none":
        return False
    return bool(state["reachable"])


def find_capture_moves(board, history=()):
    """Every legal attacker move that captures the king, confirmed by the rule engine."""
    moves = []
    for move in get_legal_moves(board, "A"):
        if check_winner(apply_move(board, move, "A"), "D") == "A":
            moves.append(move)
    return moves


def _escape_moves(board):
    king = king_square(board)
    if king is None:
        return []
    return [end for start, end in get_legal_moves(board, "D") if start == king]


def immediate_escape_count(board):
    return sum(1 for r, c in _escape_moves(board) if r in EDGE or c in EDGE)


def attacker_move_priority(board, move, child, history=(), *, escapes_before=None, completion_before=None):
    """Strategic ordering tuple for one attacker root move (higher is better).

    The components follow the priority list of the V7 attacker plan: proven win,
    immediate capture threat, blocking a direct escape, a guard capture that keeps the
    blockade, closing a capture gap, and finally generic escape/space reduction.
    """
    other = "D"
    win = check_winner(child, other) == "A"
    escapes_after = immediate_escape_count(child)
    if escapes_before is None:
        escapes_before = immediate_escape_count(board)
    if completion_before is None:
        completion_before = structure_state(board)["completion"]
    state_after = structure_state(child)
    guard_captured = sum(row.count("D") for row in child) < sum(row.count("D") for row in board)
    blocks = escapes_before > 0 and escapes_after == 0
    keeps_blockade = guard_captured and escapes_after <= escapes_before
    return (1 if win else 0,
            1 if state_after["reachable"] else 0,
            1 if blocks else 0,
            1 if keeps_blockade else 0,
            1 if state_after["completion"] > completion_before else 0,
            escapes_before - escapes_after,
            state_after["completion"] - completion_before,
            -len(state_after["gaps"]))
