"""Behavior checks for the original V5 engine used by the course entry."""
import unittest

from src.engine_process import Engine
from src.game import initial_board, is_legal_move
from src.role_player import role_spec


class AttackerCorrectnessTests(unittest.TestCase):
    def test_verified_v5_produces_deterministic_legal_moves(self):
        board = initial_board()
        spec = role_spec("A", verify_attacker=True)
        spec["nodes"] = 500
        results = []
        for _ in range(2):
            engine = Engine(spec, board)
            try:
                played = tuple(map(tuple, engine.play("A", board)))
                self.assertTrue(is_legal_move(board, played, "A"))
                results.append((played, engine.last_search_stats["score"],
                                engine.last_search_stats["completed_depth"]))
            finally:
                engine.close()
        self.assertEqual(results[0], results[1])
