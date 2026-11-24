from contextlib import redirect_stdout
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import train_selfplay
from src.game import apply_move, get_legal_moves, initial_board
from src.learning import fit_evaluator, load_evaluator
from src.search import choose_move


class LearningTests(unittest.TestCase):
    def test_fit_and_search_use_learned_evaluator(self):
        rows = [(0, 1, 0, 1, 1), (1, 0, 0, 1, -1)] * 10
        model = fit_evaluator(rows)
        self.assertLess(model.weights[0], 0)
        self.assertGreater(model.weights[1], 0)
        board = initial_board()
        self.assertEqual(model(board, "A"), -model(board, "D"))
        preferred = get_legal_moves(board, "A")[-1]
        preferred_board = apply_move(board, preferred, "A")
        self.assertEqual(
            choose_move(board, "A", strategy="greedy",
                        evaluator=lambda candidate, _: float(candidate == preferred_board)),
            preferred,
        )

    def test_resume_keeps_best_and_uses_new_candidates(self):
        def score(points):
            return {"overall": {"points": points, "games": 4, "wins": points // 2,
                               "draws": points % 2, "losses": 4 - (points + 1) // 2}}

        samples = [(0, 1, 0, 1, 1), (1, 0, 0, 1, -1)]
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), \
                patch.object(train_selfplay, "evaluate", side_effect=map(score, (2, 4, 0))), \
                patch.object(train_selfplay, "play_training_game", return_value=("D", samples)) as play:
            args = ["--output-dir", directory, "--train-games", "1", "--eval-pairs", "1"]
            train_selfplay.main(args)
            train_selfplay.main(["--output-dir", directory, "--resume", "--train-games", "2"])
            paths = train_selfplay.checkpoint_files(Path(directory))
            self.assertEqual(len(paths), 3)
            latest = train_selfplay.read_checkpoint(paths[-1])
            self.assertEqual(latest["generation"], 2)
            self.assertEqual(latest["best"]["generation"], 1)
            self.assertEqual(latest["candidate"]["generation"], 2)
            self.assertEqual(latest["config"]["train_games"], 2)
            self.assertEqual(len(latest["replay_batches"]), 2)
            self.assertIsNotNone(play.call_args.args[0]["A"])
            self.assertEqual(load_evaluator(paths[-1]).weights, tuple(latest["best"]["weights"]))
            self.assertEqual(load_evaluator(paths[-1], candidate=True).weights,
                             tuple(latest["candidate"]["weights"]))
            with self.assertRaises(FileExistsError):
                train_selfplay.save_checkpoint(Path(directory), latest)

    def test_continuous_compares_two_trials_and_stops_after_checkpoint(self):
        scores = iter((2, 3, 4))
        samples = [(0, 1, 0, 1, 1), (1, 0, 0, 1, -1)]
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), \
                patch.object(train_selfplay, "play_training_game", return_value=("D", samples)):
            run_dir = Path(directory)

            def evaluate(model, config):
                value = next(scores)
                if value == 4:
                    (run_dir / train_selfplay.STOP_FILE).touch()
                return {"overall": {"points": value, "games": 4, "wins": value // 2,
                                    "draws": value % 2, "losses": 4 - (value + 1) // 2}}

            args = ["--output-dir", directory, "--train-games", "1", "--eval-pairs", "1"]
            with patch.object(train_selfplay, "evaluate", side_effect=evaluate):
                train_selfplay.main(args + ["--continuous"])
            paths = train_selfplay.checkpoint_files(run_dir)
            self.assertEqual(len(paths), 2)
            latest = train_selfplay.read_checkpoint(paths[-1])
            self.assertEqual([trial["method"] for trial in latest["trials"]], ["blend", "perturbation"])
            self.assertEqual(latest["candidate"]["method"], "perturbation")
            self.assertEqual(latest["best"]["method"], "perturbation")

    def test_training_directory_rejects_a_second_writer_and_unlocks(self):
        with TemporaryDirectory() as directory:
            run_dir = Path(directory)
            with train_selfplay.training_lock(run_dir):
                with self.assertRaises(RuntimeError):
                    with train_selfplay.training_lock(run_dir):
                        pass
            with train_selfplay.training_lock(run_dir):
                self.assertTrue((run_dir / ".training.lock").is_file())
