"""Rule-confirmed one-move threats for diagnostics on bounded budgets."""
from dataclasses import dataclass
from time import perf_counter

from src.game import apply_move, check_winner, get_legal_moves, get_state_key, is_legal_move, king_capture_supported


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
    """All legal attacker origins for a destination, scanning backwards."""
    r, c = square
    if board[r][c] != ".":
        return ()
    origins = []
    for dr, dc in DIRECTIONS:
        row, col = r + dr, c + dc
        while 0 <= row < 9 and 0 <= col < 9:
            piece = board[row][col]
            if piece not in ".X":
                if piece == "A" and is_legal_move(board, ((row, col), square), "A"):
                    origins.append((row, col))
                break
            row, col = row + dr, col + dc
    return tuple(origins)


def _capture_axes(king):
    r, c = king
    if king in NEAR_CASTLE:
        return (("castle", tuple((r+dr,c+dc) for dr,dc in DIRECTIONS
                                 if (r+dr,c+dc) != CASTLE)),)
    return (("horizontal", ((r,c-1),(r,c+1))), ("vertical", ((r-1,c),(r+1,c))))


def structure_state(board):
    """Keep legal origins and necessary support separate for each capture axis."""
    king = king_square(board)
    region = king_region(board)
    paths = []
    if king is not None:
        for axis, squares in _capture_axes(king):
            if any(not (0 <= r < 9 and 0 <= c < 9) for r,c in squares):
                continue
            support = tuple(p for p in squares if board[p[0]][p[1]] == "A")
            gaps = tuple(p for p in squares if p not in support)
            origins = {gap: tuple(p for p in _gap_reachable(board, gap) if p not in support)
                       for gap in gaps}
            paths.append(dict(axis=axis, required=len(squares), support=support, occupied=len(support),
                              completion=len(support)/len(squares), gaps=gaps, origins=origins,
                              reachable=tuple(gap for gap in gaps if origins[gap])))
    best = max(paths,key=lambda path: (path["completion"],len(path["reachable"])),
               default=dict(required=0,occupied=0,completion=0.0,gaps=(),reachable=()))
    return dict(region=region,structures=paths,**best)


def capture_candidates(board, king):
    for dr, dc in DIRECTIONS:
        dest = (king[0]+dr, king[1]+dc)
        if not all(0 <= x < 9 for x in dest) or board[dest[0]][dest[1]] != ".":
            continue
        if king_capture_supported(board,king,dest):
            for origin in _gap_reachable(board,dest):
                if king_capture_supported(board,king,dest,origin):
                    yield origin,dest


def capture_threat_available(board, king=None):
    king = king_square(board) if king is None else king
    return king is not None and next(capture_candidates(board,king),None) is not None


def find_capture_moves(board, history=(), *, apply=apply_move):
    """Return legal king captures in a live attacker-to-move position."""
    king = king_square(board)
    if king is None or check_winner(board,"A",history) is not None:
        return []
    ancestors = tuple(history)+(get_state_key(board,"A"),)
    return [move for move in capture_candidates(board,king)
            if check_winner(apply(board,move,"A"),"D",ancestors)=="A"]


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
    win = check_winner(child, other, tuple(history)+(get_state_key(board,"A"),)) == "A"
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
            1 if capture_threat_available(child) else 0,
            1 if blocks else 0,
            1 if keeps_blockade else 0,
            1 if state_after["completion"] > completion_before else 0,
            escapes_before - escapes_after,
            state_after["completion"] - completion_before,
            -len(state_after["gaps"]))

@dataclass(frozen=True)
class CaptureProof:
    status: str
    line: tuple
    nodes: int


def prove_capture(board, history=(), *, deadline, max_nodes=1000, moves=None):
    """Prove a 3- or 5-ply attacker win using all legal defender replies."""
    work = 0

    def tick():
        if perf_counter() >= deadline or work >= max_nodes:
            raise TimeoutError

    def child(position, move, side):
        nonlocal work
        tick()
        work += 1
        return apply_move(position, move, side)

    def attack(position, path, remaining, allowed=None):
        tick()
        if remaining == 1:
            wins = find_capture_moves(position, path, apply=child)
            return (wins[0],) if wins else ()
        candidates = get_legal_moves(position, "A") if allowed is None else allowed
        next_path = (*path, get_state_key(position, "A"))
        for move in candidates:
            after = child(position, move, "A")
            outcome = check_winner(after, "D", next_path)
            if outcome == "A":
                return (move,)
            if outcome is not None or not capture_threat_available(after):
                continue
            reply_path = (*next_path, get_state_key(after, "D"))
            witness = ()
            for reply in get_legal_moves(after, "D"):
                response = child(after, reply, "D")
                if check_winner(response, "A", reply_path) is not None:
                    break
                continuation = attack(response, reply_path, remaining-2)
                if not continuation:
                    break
                line = (reply, *continuation)
                if len(line) > len(witness):
                    witness = line
            else:
                if witness:
                    return (move, *witness)
        return ()

    path = tuple(history)
    if check_winner(board,"A",path) is not None:
        return CaptureProof("NOT_PROVEN",(),0)
    try:
        for depth in (3,5):
            line = attack(board,path,depth,moves)
            if line:
                return CaptureProof("WIN",line,work)
        return CaptureProof("NOT_PROVEN",(),work)
    except TimeoutError:
        return CaptureProof("UNKNOWN",(),work)
