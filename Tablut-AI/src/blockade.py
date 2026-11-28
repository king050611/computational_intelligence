"""V7 escape, attacker-attributed control and rule-aware capture metrics."""
from functools import lru_cache

from config.settings import CASTLE, DIRECTIONS
from src.game import apply_move, check_winner, get_legal_moves, get_piece_moves, get_state_key, king_capture_supported

EDGE = {0, 8}
NEAR_CASTLE = {(4, 3), (4, 4), (4, 5), (3, 4), (5, 4)}


def king_square(board):
    return next(((r, c) for r in range(9) for c in range(9) if board[r][c] == "K"), None)


def ray_dests(board, position):
    """Squares reachable in one sliding step from ``position`` (castle passable)."""
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


def board_without_king(board):
    """The same position with the king removed from its square (castle becomes X)."""
    king = king_square(board)
    if king is None:
        return board
    grid = [list(row) for row in board]
    grid[king[0]][king[1]] = "X" if king == CASTLE else "."
    return tuple(map(tuple, grid))


def board_with_king_at(board, king, destination):
    """Position after the king moves; the castle turns into X when the king leaves it."""
    grid = [list(row) for row in board]
    grid[king[0]][king[1]] = "X" if king == CASTLE else "."
    grid[destination[0]][destination[1]] = "K"
    return tuple(map(tuple, grid))


def king_moves(board):
    king = king_square(board)
    return [] if king is None else [end for _, end in get_piece_moves(board, king, "D")]


def immediate_escape(board):
    return sum(1 for r, c in king_moves(board) if r in EDGE or c in EDGE)


def geometric_escape(board, depth=2):
    """Edge squares reachable in <=depth king moves on the *simulated* board.

    The king is removed from its starting square once, because after the first move
    that square is empty (or X when it was the castle) on every path.
    """
    king = king_square(board)
    if king is None:
        return 0
    empty = board_without_king(board)
    seen, frontier = {king}, {king}
    for _ in range(max(1, depth)):
        nxt = set()
        for position in frontier:
            for dest in ray_dests(empty, position):
                if dest not in seen:
                    nxt.add(dest)
        seen |= nxt
        frontier = nxt
    return sum(1 for r, c in seen if r in EDGE or c in EDGE)


def _king_capture_move(board):
    """One legal attacker move that captures the king, confirmed by the rule engine."""
    for move in get_legal_moves(board, "A"):
        child = apply_move(board, move, "A")
        if check_winner(child, "D") == "A":
            return move
    return None


def king_capturable(board):
    """True when an attacker can capture the king with its next move."""
    return _king_capture_move(board) is not None


def tactical_escape(board, depth=2, history=()):
    """Count defender first moves that force an escape within two defender turns.

    Every legal attacker reply is considered, including captures, interceptions
    and repetition. A guard may make the first move. The input is defender to move.
    """
    if depth not in (1, 2):
        raise ValueError("Expected one or two defender turns")
    if check_winner(board, "D", history) is not None:
        return 0
    history = set(history) | {get_state_key(board, "D")}
    count = 0
    for move in get_legal_moves(board, "D"):
        child = apply_move(board, move, "D")
        outcome = check_winner(child, "A", history)
        if outcome == "D" and any(coord in EDGE for coord in king_square(child)):
            count += 1
        elif depth == 2 and outcome is None:
            following = history | {get_state_key(child, "A")}
            if all(_escape_after_reply(apply_move(child, reply, "A"), following)
                   for reply in get_legal_moves(child, "A")):
                count += 1
    return count


def _escape_after_reply(board, history):
    outcome = check_winner(board, "D", history)
    return (outcome == "D" and any(coord in EDGE for coord in king_square(board))) or (
        outcome is None and immediate_escape(board) > 0
    )


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


def capturable_adjacent_attackers(board):
    """Adjacent attackers the defender can capture with its next move."""
    king = king_square(board)
    if king is None:
        return 0
    r, c = king
    adjacent = {(r + dr, c + dc) for dr, dc in DIRECTIONS
                if 0 <= r + dr < 9 and 0 <= c + dc < 9 and board[r + dr][c + dc] == "A"}
    if not adjacent:
        return 0
    best = 0
    for move in get_legal_moves(board, "D"):
        child = apply_move(board, move, "D")
        lost = sum(1 for (ar, ac) in adjacent if child[ar][ac] != "A")
        best = max(best, lost)
    return best


def region_of(king):
    if king is None:
        return "none"
    if king == CASTLE:
        return "castle"
    if king in NEAR_CASTLE:
        return "beside_castle"
    return "field"


def _capture_paths(king):
    r, c = king
    neighbours = [(r + dr, c + dc) for dr, dc in DIRECTIONS]
    if region_of(king) != "field":
        return [("castle", [p for p in neighbours if p != CASTLE])]
    return [("horizontal", [(r, c-1), (r, c+1)]),
            ("vertical", [(r-1, c), (r+1, c)])]


def capture_formation(board, detailed=True):
    """Select one capture structure, giving priority to verified legal finishes."""
    king = king_square(board)
    empty = dict(region=region_of(king), required=0, occupied=0, completion=0.0,
                 missing=[], reachable=[], immediate_capture=False, defender_can_break=False,
                 formation_complete=False, axis=None, paths=[])
    if king is None:
        return empty
    paths = []
    for axis, squares in _capture_paths(king):
        if not all(0 <= r < 9 and 0 <= c < 9 for r, c in squares):
            continue
        support = {p for p in squares if board[p[0]][p[1]] == "A"}
        missing = [p for p in squares if p not in support]
        reachable = set()
        winning = False
        for dest in missing:
            if board[dest[0]][dest[1]] != ".":
                continue
            for origin, piece in _first_blockers(board, dest, "ADK"):
                if piece != "A" or origin in support:
                    continue
                reachable.add(dest)
                if king_capture_supported(board, king, dest, origin):
                    winning = True
        fragile = False
        if detailed and support:
            for move in get_legal_moves(board, "D"):
                if move[0] == king:
                    continue
                child = apply_move(board, move, "D")
                if any(child[r][c] != "A" for r, c in support):
                    fragile = True
                    break
        paths.append(dict(axis=axis, required=len(squares), occupied=len(support),
                          completion=len(support)/len(squares), missing=missing,
                          reachable=sorted(reachable), immediate_capture=winning,
                          formation_complete=not missing, defender_can_break=fragile))
    if not paths:
        return empty
    best = max(paths, key=lambda path: (path["immediate_capture"], _formation_score(path)))
    return {**empty, **best} if not detailed else {**empty, **best, "paths": paths}


def _formation_score(path):
    ratio = len(path["reachable"])/max(1, len(path["missing"]))
    return max(0.0, (0.5*path["completion"] + 0.3*path["immediate_capture"]
                     + 0.2*ratio - 0.25*path["defender_can_break"]))


def _first_blockers(board, king, pieces):
    r, c = king
    for dr, dc in DIRECTIONS:
        row, col = r + dr, c + dc
        while 0 <= row < 9 and 0 <= col < 9:
            cell = board[row][col]
            if cell in pieces:
                yield (row, col), cell
                break
            row, col = row + dr, col + dc


def _remove(board, squares):
    grid = [list(row) for row in board]
    for r, c in squares:
        grid[r][c] = "."
    return tuple(map(tuple, grid))


def _control_components(board):
    king = king_square(board)
    if king is None or any(coord in EDGE for coord in king):
        return 0, 0, 0, (), ()
    blockers = list(_first_blockers(board, king, "AD"))
    direct = tuple(p for p, piece in blockers if piece == "A")
    defenders = tuple(p for p, piece in blockers if piece == "D")
    attackers = tuple((r,c) for r, row in enumerate(board) for c, cell in enumerate(row) if cell == "A")
    actual = geometric_escape(board)
    without = geometric_escape(_remove(board, attackers)) if attackers else actual
    denied = (without-actual)/max(1, without)
    return len(defenders), len(direct), denied, attackers, direct


@lru_cache(maxsize=8192)
def _fast_control_score(board):
    """Cheap attacker-attributed geometry for leaf evaluation."""
    _, direct, denied, _, _ = _control_components(board)
    return round(0.30*direct/4 + 0.70*denied, 3)



def control_score(board):
    return _fast_control_score(tuple(tuple(row) for row in board))


def control_details(board):
    """Find exterior blockers and verify whether a defender capture breaks their control."""
    own, direct, denied, attackers, direct_squares = _control_components(board)
    if not attackers:
        return dict(self_blockade=own, attacker_blockade=direct, controlled_corridor=0,
                    open_corridors=0, key_blockers=[], unstable_blockers=[], stable_blockade=False)
    actual = geometric_escape(board)
    key = set(direct_squares)
    key.update(p for p in attackers if p not in key and geometric_escape(_remove(board, [p])) > actual)
    vulnerable = set()
    interceptable = total = 0
    for move in get_legal_moves(board, "D"):
        child = apply_move(board, move, "D")
        captured = {p for p in key if child[p[0]][p[1]] != "A"}
        if captured:
            restored = [list(row) for row in child]
            for r, c in captured:
                restored[r][c] = "A"
            if geometric_escape(child) > geometric_escape(restored):
                vulnerable.update(captured)
        if check_winner(child, "A") is None and immediate_escape(child):
            total += 1
            if any(not _escape_after_reply(apply_move(child, reply, "A"), ())
                   for reply in get_legal_moves(child, "A")):
                interceptable += 1
    return dict(self_blockade=own, attacker_blockade=direct, controlled_corridor=interceptable,
                open_corridors=total, key_blockers=sorted(key), unstable_blockers=sorted(vulnerable),
                stable_blockade=bool(key) and not vulnerable and not immediate_escape(board) and total == interceptable)


def capture_score(board, detailed=True):
    return round(_formation_score(capture_formation(board, detailed)), 3)


def classify(board, history=()):
    """Two-dimensional label: control and capture are judged separately."""
    control = control_score(board)
    formation = capture_formation(board)
    capture = round(_formation_score(formation), 3)
    control_label = "controlled" if control >= 0.75 else "leaky"
    capture_label = "capture_ready" if capture >= 0.5 else "no_capture"
    return dict(control=control, capture=capture,
                control_label=control_label, capture_label=capture_label,
                immediate_escape=immediate_escape(board),
                geometric_escape=geometric_escape(board, 2),
                tactical_escape=tactical_escape(board, 2, history),
                **control_details(board),
                king_moves=len(king_moves(board)),
                adjacent_attackers=adjacent_attackers(board),
                region=region_of(king_square(board)),
                formation=formation)


def snapshot(board):
    """Flat indicator row used by the analysis scripts."""
    data = classify(board)
    formation = data.pop("formation")
    data.update(immediate_capture=formation["immediate_capture"],
                formation_completion=formation["completion"],
                formation_missing=len(formation["missing"]),
                formation_reachable=len(formation["reachable"]),
                defender_can_break=formation["defender_can_break"])
    return data
