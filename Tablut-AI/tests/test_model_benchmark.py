"""Model CLI compatibility without running training or importing optional NumPy."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark


class FinishedGame:
    winner = "DRAW"
    rounds_played = 0

    def play(self, attacker, defender):
        pass


class ModelBenchmarkTests(unittest.TestCase):
    def run_cli(self, arguments):
        with patch("sys.argv", ["benchmark.py", *arguments]), redirect_stdout(io.StringIO()):
            benchmark.main()

    def test_plain_adaptive_keeps_original_player_and_output(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(benchmark, "ROOT", Path(directory)), \
                patch.object(benchmark, "Tablut", FinishedGame), \
                patch.object(benchmark, "Player") as player:
            self.run_cli(["--games", "1"])
            player.assert_called_once_with()
            path = Path(directory) / "reports/experiments/latest_v2.json"
            data = json.loads(path.read_text())
            self.assertEqual(data["strategy"], "adaptive")
            self.assertNotIn("model", data)

    def test_trained_adaptive_uses_strategy_bot_and_separate_outputs(self):
        evaluator = object()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(benchmark, "ROOT", Path(directory)), \
                patch.object(benchmark, "Tablut", FinishedGame), \
                patch.object(benchmark, "load_evaluator", return_value=evaluator), \
                patch.object(benchmark, "Player") as player, \
                patch.object(benchmark, "StrategyBot") as strategy:
            for _ in range(2):
                self.run_cli(["--model", "checkpoint.json", "--games", "1"])
            player.assert_not_called()
            strategy.assert_any_call("adaptive", 42, evaluator=evaluator)
            outputs = list((Path(directory) / "reports/experiments").glob("selfplay_seed42_*.json"))
            self.assertEqual(len(outputs), 2)
            for path in outputs:
                data = json.loads(path.read_text())
                self.assertEqual(data["strategy"], "adaptive")
                self.assertEqual(data["model_selection"], "best")

    def test_incompatible_model_arguments_fail_before_loading(self):
        cases = [
            ["--neural-model", "net.npz", "--strategy", "adaptive"],
            ["--candidate"],
            ["--model", "model.json", "--strategy", "random"],
            ["--model", "model.json", "--neural-model", "net.npz"],
            ["--opponent-model", "model.json", "--opponent", "first"],
        ]
        for args in cases:
            with self.subTest(args=args), redirect_stderr(io.StringIO()), \
                    patch.object(benchmark, "load_evaluator") as load, \
                    self.assertRaises(SystemExit) as stopped:
                self.run_cli(args)
            self.assertEqual(stopped.exception.code, 2)
            load.assert_not_called()

    def test_missing_or_malformed_models_report_cli_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.json"
            for contents in (None, "not json", '{"schema_version":1,"best":{}}'):
                if contents is not None:
                    model.write_text(contents)
                with self.subTest(contents=contents), redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit) as stopped:
                    self.run_cli(["--model", str(model), "--games", "1"])
                self.assertEqual(stopped.exception.code, 2)
