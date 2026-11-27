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
