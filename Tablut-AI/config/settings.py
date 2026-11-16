"""Fixed rules and official board encoding; coordinates are (row, column)."""
BOARD_SIZE = 9
CASTLE = (4, 4)
EMPTY = "."
CASTLE_SYMBOL = "X"
ATTACKER = "A"
DEFENDER = "D"
KING = "K"
ATTACKER_COUNT = 16
DEFENDER_COUNT = 8
DIRECTIONS = ((-1, 0), (0, -1), (1, 0), (0, 1))
INITIAL_BOARD = (
    "...AAA...", "....A....", "....D....", "A...D...A",
    "AADDKDDAA", "A...D...A", "....D....", "....A....", "...AAA...",
)

"""Search parameters; depth and pruning are reserved for a future version."""
SEARCH_DEPTH = 2
ENABLE_ALPHA_BETA = True
ENABLE_MOVE_ORDERING = True
GAME_TIME_LIMIT = 60.0
TIME_SAFETY_MARGIN = 5.0

"""Initial examples only; not tuned."""
ATTACKER_WEIGHTS = {"king_pressure": 100, "king_escape_risk": -150, "piece_advantage": 10}
DEFENDER_WEIGHTS = {"king_safety": 100, "escape_routes": 150, "piece_advantage": 10}
