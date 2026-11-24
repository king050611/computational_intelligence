"""Official adapter. Create a new Player for each game."""
from time import perf_counter
from config.settings import ENABLE_ADAPTIVE_SEARCH
from src.game import parse_board
from src.search import TimeManager, choose_move


class Player:
    def __init__(self, record_search=False, *, evaluator=None):
        self.clock = TimeManager()
        self.record_search = record_search
        self.evaluator = evaluator
        self.last_search_stats = None

    def _play(self, board, player):
        self.last_search_stats = None
        stats = {} if self.record_search else None
        start = perf_counter()
        try:
            move = choose_move(parse_board(board), player, self.clock.deadline(),
                               strategy="adaptive" if ENABLE_ADAPTIVE_SEARCH else "minimax",
                               stats=stats, evaluator=self.evaluator)
            if move is None:
                raise ValueError("No legal move: game should already be over")
            return [list(move[0]), list(move[1])]
        finally:
            elapsed = perf_counter() - start
            self.clock.record_elapsed(elapsed)
            if stats is not None:
                stats["elapsed_seconds"] = elapsed
                self.last_search_stats = stats

    def play_attacker(self, board):
        return self._play(board, "A")

    def play_defender(self, board):
        return self._play(board, "D")
