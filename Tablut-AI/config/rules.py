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
