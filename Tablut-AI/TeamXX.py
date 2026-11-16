"""Official adapter. Create a new Player for each game."""
from time import perf_counter
from config.settings import ENABLE_ADAPTIVE_SEARCH
from src.game import parse_board
from src.search import TimeManager, choose_move


class Player:
    def __init__(self):
        self.clock = TimeManager()

    def _play(self, board, player):
        start = perf_counter()
        try:
            move = choose_move(parse_board(board), player, self.clock.deadline(),
                               strategy="adaptive" if ENABLE_ADAPTIVE_SEARCH else "minimax")
            if move is None:
                raise ValueError("No legal move: game should already be over")
            return [list(move[0]), list(move[1])]
        finally:
            self.clock.record_elapsed(perf_counter() - start)

    def play_attacker(self, board):
        return self._play(board, "A")

    def play_defender(self, board):
        return self._play(board, "D")
