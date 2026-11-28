"""Unified course adapter with time management and turn-aware history."""
from time import perf_counter

from random import Random
from config.experimental import SearchOptions, AVAILABLE_STRATEGIES
from config.settings import GAME_TIME_LIMIT, TIME_SAFETY_MARGIN
from src.enhanced_search import choose_enhanced
from src.game import apply_move, get_legal_moves, get_state_key, parse_board
from src.time_control import TimeManager
from src.tactics import is_urgent
from src.tactics import opponent
from src.time_control import AdaptiveTimeManager


class ExperimentalPlayer:
    def __init__(self, strategy, *, opening=None, options=None, record_search=False, evaluator=None, seed=42):
        if strategy not in AVAILABLE_STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy}")
        if (strategy == "evolutionary_dynamic") != (evaluator is not None):
            raise ValueError("Only evolutionary_dynamic requires a six-feature model")
        self.evaluator, self.rng = evaluator, Random(seed)
        self.strategy = strategy
        self.options = options if options is not None else SearchOptions()
        self.clock = AdaptiveTimeManager() if strategy in ("enhanced_dynamic", "evolutionary_dynamic") else TimeManager()
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
            if self.options.node_budget:
                # Fixed-node experiment mode: reproducible decisions, wall clock only as a guard.
                remaining = max(1.0, GAME_TIME_LIMIT - TIME_SAFETY_MARGIN - getattr(self.clock, "spent", 0.0))
                hard = start + remaining
            elif isinstance(self.clock, AdaptiveTimeManager):
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
                stats.update(strategy=self.strategy, budget_seconds=hard - start)
            move = self.rng.choice(moves) if self.strategy == "random" else choose_enhanced(
                board, side, evaluator=self.evaluator, deadline=hard, soft_deadline=soft,
                history=self.history, stats=stats, options=self.options, moves=moves,
            )
            if stats is not None and self.strategy == "random":
                stats.update(completed_depth=0, target_depth=0, nodes=0, timed_out=False, fallback_used=False, finish_reason="random_test_baseline")
            if move not in moves:
                raise ValueError("Search did not return a legal move")
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
