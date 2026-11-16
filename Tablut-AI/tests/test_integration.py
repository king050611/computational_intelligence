import copy
import unittest
from Tablut import Tablut
from TeamXX import Player
from src.core.state import GameState
from src.core.move_generator import get_legal_moves


class IntegrationTests(unittest.TestCase):
    def test_official_full_game_and_no_input_mutation(self):
        game, player = Tablut(), Player()
        game.past_positions = [game.compute_zobrist_hash(True)]
        for ply in range(500):
            attacker = ply % 2 == 0
            before = copy.deepcopy(game.board)
            move = (player.play_attacker if attacker else player.play_defender)(game.board)
            self.assertEqual(game.board, before)
            self.assertIsInstance(move, list)
            self.assertTrue(all(isinstance(p, list) for p in move))
            self.assertTrue(game.make_move(attacker, move))
            if game.check_if_game_over(not attacker):
                break
        else:
            self.fail("Baseline game did not finish within 500 plies")

    def test_moves_on_reachable_positions_match_framework(self):
        import random
        rng, game = random.Random(42), Tablut()
        for ply in range(50):
            attacker = ply % 2 == 0
            moves = get_legal_moves(GameState(game.board, "A" if attacker else "D"))
            for move in moves:
                probe = copy.copy(game)
                self.assertTrue(probe.make_move(attacker, move))
            if not moves:
                break
            self.assertTrue(game.make_move(attacker, rng.choice(moves)))
            if game.check_if_game_over(not attacker):
                break
