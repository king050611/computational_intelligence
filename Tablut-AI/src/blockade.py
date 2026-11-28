"""V7 Phase 2 analysis-only metrics: escape levels, control, region-aware capture.

Design notes (fixes from the Phase 1 review):

* ``immediate_escape``   - one king move reaches an edge; a win for the defender.
* ``geometric_escape``   - edge squares reachable in <=N king moves, simulating the
  board **after each king step** (the vacated square becomes empty, or X when the king
  leaves the castle). Guards do not move and attackers do not reply: this is explicitly
  a geometric bound, not a threat assessment.
* ``tactical_escape``    - the same two-step bound, but a route is discarded when the
  attacker could capture the king on the intermediate square. This still ignores the
  attacker's *blocking* replies, so it is a lower bound on real safety; anything that
  needs full replies belongs to search, not to a leaf evaluator.

* ``control_score`` and ``capture_score`` are separate on purpose: a position can be
  fully controlled without a single attacker touching the king, and it can have a
  capture formation without controlling an escape. The Phase 1 single label conflated
  the two, which the review correctly flagged.

* ``capture_formation`` follows the three referee regions (castle / beside-castle /
  open board) and reports what is missing, what is reachable next move, and whether the
  defender could break the formation. Actual capture is always confirmed by the rule
  engine (``check_winner``), never inferred.

Nothing in this module is imported by the search or the evaluator.
"""
from config.settings import CASTLE, DIRECTIONS
from src.game import apply_move, check_winner, get_legal_moves, get_piece_moves

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


def tactical_escape(board, depth=2):
    """Two-step escapes whose intermediate square is not already a capture for the attacker."""
    king = king_square(board)
    if king is None:
        return 0
    first_moves = king_moves(board)
    edges = set()
    for first in first_moves:
        if first[0] in EDGE or first[1] in EDGE:
            edges.add(first)
            continue
        if depth < 2:
            continue
        after_first = board_with_king_at(board, king, first)
        if king_capturable(after_first):
            continue
        for second in king_moves(after_first):
            if second[0] in EDGE or second[1] in EDGE:
                edges.add(second)
    return len(edges)


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


def capture_formation(board):
    """Region-aware capture requirement, progress, reachability and defender counter-play."""
    king = king_square(board)
    empty = dict(region="none", required=0, occupied=0, completion=0.0, missing=[],
                 reachable=[], immediate_capture=False, defender_can_break=False)
    if king is None:
        return empty
    r, c = king
    region = region_of(king)
    neighbours = [(r + dr, c + dc) for dr, dc in DIRECTIONS]
    in_board = [square for square in neighbours if 0 <= square[0] < 9 and 0 <= square[1] < 9]
    enemy_pieces = "AX" if region in ("castle", "beside_castle") else "AX"
    occupied = [square for square in in_board if board[square[0]][square[1]] in enemy_pieces]
    missing = [square for square in in_board if square not in occupied]

    if region in ("castle", "beside_castle"):
        required = len(in_board)
        completion = len(occupied) / required if required else 0.0
        complete = len(missing) == 0
    else:
        # Open board: a capture needs an opposing pair with at least one attacker.
        pairs = [((dr, dc), (-dr, -dc)) for dr, dc in DIRECTIONS]
        best = 0
        for (dr, dc), (dr2, dc2) in pairs:
            first, second = (r + dr, c + dc), (r + dr2, c + dc2)
            if not all(0 <= y < 9 and 0 <= x < 9 for y, x in (first, second)):
                continue
            values = (board[first[0]][first[1]], board[second[0]][second[1]])
            score = sum(1 for value in values if value in "AX")
            if "A" in values:
                best = max(best, score)
        required = 2
        completion = best / required
        complete = best == 2

    attackers = [position for position in in_board if board[position[0]][position[1]] == "A"]
    reachable = []
    for square in missing:
        for move in get_legal_moves(board, "A"):
            if move[1] == square:
                reachable.append(square)
                break
    capture_move = _king_capture_move(board)
    empty.update(region=region, required=required, occupied=len(occupied),
                 completion=round(completion, 3), missing=missing, reachable=reachable,
                 immediate_capture=capture_move is not None,
                 defender_can_break=capturable_adjacent_attackers(board) > 0,
                 formation_complete=complete)
    return empty


def control_score(board):
    """[0,1] containment of the king, independent of whether a capture is available."""
    king = king_square(board)
    if king is None:
        return 0.0
    immediate = 1.0 if immediate_escape(board) == 0 else 0.0
    geometric = 1.0 if geometric_escape(board, 2) == 0 else 0.0
    mobility = max(0.0, 1.0 - len(king_moves(board)) / 4)
    r, c = king
    rays = 0
    for dr, dc in DIRECTIONS:
        row, col = r + dr, c + dc
        while 0 <= row < 9 and 0 <= col < 9:
            if board[row][col] in "ADK":
                if board[row][col] == "A":
                    rays += 1
                break
            row += dr
            col += dc
    return round(0.4 * immediate + 0.3 * geometric + 0.15 * mobility + 0.15 * (rays / 4), 3)


def capture_score(board):
    """[0,1] how close the attacker is to a legal capture, penalised when it is fragile."""
    formation = capture_formation(board)
    if formation["region"] == "none":
        return 0.0
    progress = 0.5 * formation["completion"]
    progress += 0.3 if formation["immediate_capture"] else 0.0
    progress += 0.2 * (len(formation["reachable"]) / max(1, len(formation["missing"]))) if formation["missing"] else 0.2
    if formation["defender_can_break"]:
        progress -= 0.25
    return round(max(0.0, min(1.0, progress)), 3)


def classify(board):
    """Two-dimensional label: control and capture are judged separately."""
    control = control_score(board)
    capture = capture_score(board)
    control_label = "controlled" if control >= 0.75 else "leaky"
    capture_label = "capture_ready" if capture >= 0.5 else "no_capture"
    return dict(control=control, capture=capture,
                control_label=control_label, capture_label=capture_label,
                immediate_escape=immediate_escape(board),
                geometric_escape=geometric_escape(board, 2),
                tactical_escape=tactical_escape(board, 2),
                king_moves=len(king_moves(board)),
                adjacent_attackers=adjacent_attackers(board),
                region=region_of(king_square(board)),
                formation=capture_formation(board))


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
