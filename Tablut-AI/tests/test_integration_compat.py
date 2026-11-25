"""Frozen v2.2 search outcomes, generated before optional learning integration.

The fixture records moves, scores and statistics from stable commit b51abfd.
Tests require neither Git nor NumPy, and use controlled timeouts rather than
machine speed to check partially completed search iterations.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from src import search
from src.game import get_state_key
from src.learning import load_evaluator


FIXTURE = json.loads((Path(__file__).with_name("fixtures") / "search_v2_2.json")
                     .read_text(encoding="utf-8"))
BOARDS = {name: tuple(map(tuple, rows)) for name, rows in FIXTURE["boards"].items()}


class AssessmentCompatibilityTests(unittest.TestCase):
    def choose(self, case, *, explicit_defaults=False):
        stats = {}
        controls = case["controls"]
        with ExitStack() as stack:
            stack.enter_context(patch.object(search, "perf_counter", return_value=0.0))
            if "checks" in controls:
                checks = [0]

                def check_time(deadline):
                    if checks[0] >= controls["checks"]:
                        raise search.SearchTimeout()
                    checks[0] += 1

                stack.enter_context(patch.object(search, "_check_time", side_effect=check_time))
            if "interrupt_depth" in controls:
                stack.enter_context(patch.object(search, "is_urgent", return_value=True))
                stack.enter_context(patch.object(search, "DEEP_SEARCH_MAX_BRANCHES", 1000))

                def controlled_score(*args, **kwargs):
                    if args[3] == controls["interrupt_depth"]:
                        raise search.SearchTimeout()
                    return 1

                stack.enter_context(patch.object(search, "alpha_beta", side_effect=controlled_score))
            kwargs = dict(evaluator=None, history=(), position_value=None) if explicit_defaults else {}
            move = search.choose_move(
                BOARDS[case["board"]], case["side"], strategy=case["strategy"],
                rng=random.Random(FIXTURE["rng_seed"]), stats=stats, **kwargs)
        return None if move is None else [list(square) for square in move], stats

    def test_default_moves_and_all_statistics_match_stable_v2_2(self):
        for case in FIXTURE["choose"]:
            with self.subTest(board=case["board"], side=case["side"],
                              strategy=case["strategy"], controls=case["controls"]):
                move, stats = self.choose(case)
                self.assertEqual(move, case["move"])
                self.assertEqual(stats, case["stats"])

    def test_explicit_optional_defaults_preserve_assessment_behavior(self):
        for case in FIXTURE["choose"]:
            with self.subTest(board=case["board"], side=case["side"],
                              strategy=case["strategy"], controls=case["controls"]):
                self.assertEqual(self.choose(case, explicit_defaults=True),
                                 (case["move"], case["stats"]))

    def test_alpha_beta_scores_nodes_and_repetition_match_stable_v2_2(self):
        for case in FIXTURE["alpha_beta"]:
            with self.subTest(side=case["side"], root=case["root"], repeated=case["repeated"]):
                board = BOARDS[case["board"]]
                path = (get_state_key(board, case["side"]),) if case["repeated"] else ()
                stats = {}
                value = search.alpha_beta(
                    board, case["side"], case["root"], case["depth"],
                    -float("inf"), float("inf"), float("inf"), path, stats=stats)
                self.assertEqual(value, case["value"])
                self.assertEqual(stats, case["stats"])


class LinearCheckpointValidationTests(unittest.TestCase):
    def test_missing_and_corrupt_linear_checkpoints_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            with self.assertRaises(FileNotFoundError):
                load_evaluator(path)
            path.write_text("not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_evaluator(path)

    def test_invalid_weights_are_rejected_and_null_best_preserves_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            for weights in ([1, 2], [1, 2, 3, "bad"], [1, 2, 3, float("inf")]):
                with self.subTest(weights=weights):
                    path.write_text(json.dumps(dict(schema_version=1, best=dict(weights=weights))),
                                    encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_evaluator(path)
            path.write_text(json.dumps(dict(schema_version=1, best=dict(weights=None),
                                            candidate=dict(weights=[1, 2, 3, 4]))), encoding="utf-8")
            self.assertIsNone(load_evaluator(path))
            self.assertEqual(load_evaluator(path, candidate=True).weights, (1, 2, 3, 4))
