"""V5-D: eight evaluation features and the six-to-eight weight migration."""
import json
import unittest
from math import fsum
from pathlib import Path
import tempfile

from config.evolution import BASE_WEIGHTS, GENE_SIGNS
from src.evaluation import (FEATURE_NAMES, LEGACY_FEATURES, SCHEMA_VERSION, WeightedEvaluator,
                            load_evaluator, migrate_weights, model_record)
from src.features import (extract_features, immediate_king_threat, king_escape_distance)
from src.game import initial_board


def position(pieces):
    board = [["."] * 9 for _ in range(9)]
    board[4][4] = "X"
    for (r, c), piece in pieces.items():
        board[r][c] = piece
    return tuple(map(tuple, board))


class FeatureVectorTests(unittest.TestCase):
    def test_eight_features_and_eight_genes(self):
        self.assertEqual(len(FEATURE_NAMES), 8)
        self.assertEqual(len(BASE_WEIGHTS), 8)
        self.assertEqual(len(GENE_SIGNS), 8)
        self.assertEqual(extract_features(initial_board()).__len__(), 8)
        # The two new genes start at zero so behaviour is unchanged until training.
        self.assertEqual(BASE_WEIGHTS[6:], (0.0, 0.0))

    def test_legacy_equivalence_of_zero_weighted_features(self):
        board = initial_board()
        old = fsum(w * f for w, f in zip(BASE_WEIGHTS[:6], extract_features(board)[:6]))
        new = WeightedEvaluator(BASE_WEIGHTS)(board, "D")
        self.assertAlmostEqual(old, new)

    def test_escape_distance_reacts_to_blockers_and_edges(self):
        clear = position({(4, 4): "K"})
        blocked = position({(4, 4): "K", (4, 2): "A"})
        near_edge = position({(4, 2): "K"})
        self.assertLess(king_escape_distance(near_edge, (4, 2)), king_escape_distance(clear, (4, 4)))
        self.assertGreaterEqual(king_escape_distance(blocked, (4, 4)), king_escape_distance(clear, (4, 4)) / 2)
        self.assertLessEqual(king_escape_distance(clear, (4, 4)), 1.0)

    def test_immediate_threat_detects_a_capturable_king(self):
        danger = position({(2, 2): "K", (2, 0): "A", (2, 3): "A"})
        safe = position({(2, 2): "K", (2, 0): "A"})
        self.assertEqual(immediate_king_threat(danger, (2, 2)), 1.0)
        self.assertEqual(immediate_king_threat(safe, (2, 2)), 0.0)

    def test_features_stay_bounded(self):
        for board, side in ((initial_board(), "A"), (position({(2, 2): "K", (2, 1): "A", (2, 3): "A"}), "D")):
            values = extract_features(board)
            self.assertEqual(len(values), 8)
            self.assertTrue(all(isinstance(v, float) for v in values))
            self.assertTrue(all(-1.0 <= v <= 4.0 for v in values))


class SchemaMigrationTests(unittest.TestCase):
    def test_migrate_pads_legacy_vectors(self):
        legacy = (-400.0, 600.0, -160.0, 0.0, 0.0, 0.0)
        self.assertEqual(migrate_weights(legacy), legacy + (0.0, 0.0))
        self.assertEqual(migrate_weights(BASE_WEIGHTS), tuple(BASE_WEIGHTS))
        for bad in (legacy[:-1], (1.0,) * 7, (1.0,) * 9):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                migrate_weights(bad)

    def test_schema_one_model_loads_as_migrated_eight_gene(self):
        legacy = (-400.0, 600.0, -160.0, 0.0, 0.0, 0.0)
        record = dict(schema_version=1, model_type="evolutionary_dynamic",
                      features=list(LEGACY_FEATURES), weights=list(legacy))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            evaluator = load_evaluator(path)
        self.assertTrue(evaluator.migrated)
        self.assertEqual(evaluator.weights, legacy + (0.0, 0.0))
        self.assertEqual(WeightedEvaluator(BASE_WEIGHTS)(initial_board(), "D"),
                         evaluator(initial_board(), "D"))

    def test_schema_two_model_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            path.write_text(json.dumps(model_record(BASE_WEIGHTS, generation=2)), encoding="utf-8")
            evaluator = load_evaluator(path)
            record = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(evaluator.migrated)
        self.assertEqual(record["schema_version"], SCHEMA_VERSION)
        self.assertEqual(record["features"], list(FEATURE_NAMES))
        self.assertEqual(len(record["weights"]), 8)

    def test_wrong_feature_order_or_length_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            cases = [
                dict(schema_version=2, model_type="evolutionary_dynamic",
                     features=list(FEATURE_NAMES)[:-1] + ["king_pressure"], weights=[0.0] * 8),
                dict(schema_version=2, model_type="evolutionary_dynamic",
                     features=list(FEATURE_NAMES), weights=[0.0] * 6),
                dict(schema_version=1, model_type="evolutionary_dynamic",
                     features=list(LEGACY_FEATURES), weights=[0.0] * 8),
                dict(schema_version=3, model_type="evolutionary_dynamic",
                     features=list(FEATURE_NAMES), weights=[0.0] * 8),
            ]
            for index, record in enumerate(cases):
                with self.subTest(case=index):
                    path.write_text(json.dumps(record), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_evaluator(path)

    def test_evaluator_rejects_seven_and_nine_genes(self):
        for length in (7, 9, 6):
            with self.subTest(length=length), self.assertRaises(ValueError):
                WeightedEvaluator((1.0,) * length)


if __name__ == "__main__":
    unittest.main()
