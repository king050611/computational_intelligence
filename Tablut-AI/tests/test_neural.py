import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.game import apply_move, get_legal_moves, initial_board
from src.neural import Network, Sample, action_id, encode_board, load_network, save_network
from src.neural_player import NeuralPlayer, monte_carlo_search
from src.search import alpha_beta


class NeuralTests(unittest.TestCase):
    def setUp(self):
        self.board = initial_board()
        self.model = Network.initialize(7)
        self.rng = np.random.default_rng(7)

    def test_full_board_and_turn_are_encoded(self):
        move = get_legal_moves(self.board, "A")[0]
        changed = apply_move(self.board, move, "A")
        self.assertFalse(np.array_equal(encode_board(self.board, "A"), encode_board(changed, "A")))
        self.assertFalse(np.array_equal(encode_board(self.board, "A"), encode_board(self.board, "D")))

    def test_training_updates_value_and_policy_and_roundtrips(self):
        actions = [action_id(move) for move in get_legal_moves(self.board, "A")[:2]]
        policy = tuple(zip(actions, (1.0, 0.0)))
        samples = [Sample(self.board, "A", 1.0, policy)] * 8
        before, priors = self.model.predict(self.board, "A", actions)
        self.model.fit(samples, epochs=8, rng=self.rng, learn_policy=True)
        after, new_priors = self.model.predict(self.board, "A", actions)
        self.assertGreater(after, before)
        self.assertGreater(new_priors[0], priors[0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.npz"
            metadata = {"schema_version": 1, "phase": "policy"}
            save_network(path, self.model, metadata)
            loaded, saved = load_network(path)
            self.assertEqual(saved, metadata)
            value, loaded_priors = loaded.predict(self.board, "A", actions)
            self.assertEqual(value, after)
            np.testing.assert_array_equal(loaded_priors, new_priors)

    def test_search_uses_leaf_turn_and_root_perspective(self):
        seen = []

        def value(board, side):
            seen.append(side)
            return 0.25

        args = (self.board, "D", "A", 0, -float("inf"), float("inf"), float("inf"))
        self.assertEqual(alpha_beta(*args, position_value=value), -0.25)
        self.assertEqual(seen, ["D"])

    def test_mcts_returns_legal_probability_distribution_for_both_sides(self):
        for side in ("A", "D"):
            legal = get_legal_moves(self.board, side)
            move, policy = monte_carlo_search(self.model, self.board, side, 8,
                                              noise=self.rng, sample_move=True)
            self.assertIn(move, legal)
            self.assertEqual({action for action, _ in policy}, {action_id(move) for move in legal})
            self.assertEqual(len(policy), len({action for action, _ in policy}))
            self.assertAlmostEqual(sum(probability for _, probability in policy), 1)

    def test_value_player_uses_course_move_format(self):
        player = NeuralPlayer(self.model, "value", 8)
        move = player.play_attacker(self.board)
        self.assertIsInstance(move, list)
        self.assertIn(tuple(map(tuple, move)), get_legal_moves(self.board, "A"))
