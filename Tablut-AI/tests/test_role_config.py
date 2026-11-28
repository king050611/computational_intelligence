"""Deployment and opponent pool pins for independent role builds."""
import json
from pathlib import Path
import unittest

from src.game import apply_move, get_legal_moves, initial_board, is_legal_move
from src.role_player import RolePlayer, ROOT, role_spec
from scripts.train_role import model_spec


class RoleConfigPinTests(unittest.TestCase):
    def test_candidate_engine_and_model_match_source(self):
        self.assertEqual(role_spec("A", verify_attacker=True)["depth"], 4)

    def test_defender_engine_and_model_match_source(self):
        self.assertEqual(role_spec("D")["seconds"], 60)

    def test_frozen_defender_pool(self):
        path = ROOT / "config/defender_pool.json"
        entries = json.loads(path.read_bytes())
        self.assertEqual([entry["share"] for entry in entries], [30, 30, 25, 15])
        for entry in entries:
            spec = model_spec(path.parent / entry["engine"], path.parent / entry["model"],
                              entry["depth"], entry["seconds"])
            self.assertEqual(spec["files"], entry["files"])
            self.assertEqual(spec["model_sha256"], entry["model_sha256"])

    def test_role_engines_keep_separate_process_state(self):
        board = initial_board()
        with RolePlayer() as player:
            played = player.play_attacker(board)
            self.assertTrue(is_legal_move(board, played, "A"))
            board = apply_move(board, played, "A")
            self.assertTrue(is_legal_move(board, player.play_defender(board), "D"))
            self.assertNotEqual(player._engines["A"].process.pid, player._engines["D"].process.pid)

    def test_formal_rollback_still_available(self):
        from TeamXX import LegacyPlayer, Player, independent_player
        self.assertEqual(LegacyPlayer().strategy, "enhanced_dynamic")
        self.assertIsInstance(Player(), RolePlayer)
        with independent_player() as player:
            self.assertIsInstance(player, RolePlayer)
