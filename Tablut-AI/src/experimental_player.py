"""Course-facing adapter for opt-in searches and turn-aware game history."""
from time import perf_counter

from config.experimental import SearchOptions
from src.experimental_search import choose_experimental_move
from src.game import apply_move, get_legal_moves, get_state_key, parse_board
from src.search import TimeManager, is_urgent
from src.tactics import opponent
from src.time_control import AdaptiveTimeManager


class ExperimentalPlayer:
    def __init__(self, strategy, *, opening=None, options=None, record_search=False):
        self.strategy = strategy
        self.options = options if options is not None else SearchOptions()
        self.clock = AdaptiveTimeManager() if strategy == "enhanced_dynamic" else TimeManager()
        self.history = []
        self.opening = opening
        self.record_search = record_search
        self.last_search_stats = None

    def _play(self, board, side):
        start = perf_counter()
        stats = {} if self.record_search else None
        self.last_search_stats = None
        try:
            board = parse_board(board)
            if not self.history and self.opening is not None and side == "D":
                self.history.append(get_state_key(self.opening, "A"))
            moves = get_legal_moves(board, side)
            soft = None
            if isinstance(self.clock, AdaptiveTimeManager):
                _, maximum = self.clock.deadlines(start, 1.6)
                complexity = 1.0
                if len(moves) == 1:
                    complexity = 0.6
                elif perf_counter() < maximum and is_urgent(board):
                    complexity = 1.6
                soft, hard = self.clock.deadlines(start, complexity)
            else:
                hard = start + self.clock.allocate_time()
            if stats is not None:
                stats["budget_seconds"] = hard - start
            move = choose_experimental_move(
                board, side, strategy=self.strategy, deadline=hard, soft_deadline=soft,
                history=self.history, stats=stats, options=self.options, moves=moves,
            )
            if move not in moves:
                raise ValueError("Experimental search did not return a legal move")
            self.history.extend((get_state_key(board, side),
                                 get_state_key(apply_move(board, move, side), opponent(side))))
            return [list(square) for square in move]
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
