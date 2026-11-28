"""Fixed rules and official board encoding; coordinates are (row, column)."""
BOARD_SIZE = 9
CASTLE = (4, 4)
DIRECTIONS = ((-1, 0), (0, -1), (1, 0), (0, 1))
INITIAL_BOARD = (
    "...AAA...", "....A....", "....D....", "A...D...A",
    "AADDKDDAA", "A...D...A", "....D....", "....A....", "...AAA...",
)

"""Search limits for v2 iterative deepening."""
GAME_TIME_LIMIT = 60.0
TIME_SAFETY_MARGIN = 5.0

"""Initial examples only; not tuned."""
ATTACKER_WEIGHTS = {"king_pressure": 100, "king_escape_risk": -150, "piece_advantage": 10}
DEFENDER_WEIGHTS = {"king_safety": 100, "escape_routes": 150, "piece_advantage": 10}
