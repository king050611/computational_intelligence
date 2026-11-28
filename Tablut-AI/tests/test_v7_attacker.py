import json
from pathlib import Path
import unittest

from scripts.build_corpus import validate
from src.blockade import capture_formation, control_details, control_score, tactical_escape
from src.evaluation import AttackerStrategyEvaluator, WeightedEvaluator
from src.game import get_state_key, initial_board


def position(pieces):
    grid = [list(".........") for _ in range(9)]
    grid[4][4] = "X"
    for (r, c), piece in pieces.items():
        grid[r][c] = piece
    return tuple(map(tuple, grid))


class AttackerStrategyTests(unittest.TestCase):
    def test_initial_guards_do_not_count_as_attacker_control(self):
        board = initial_board()
        self.assertEqual(control_score(board), 0)
        self.assertEqual(control_details(board)["self_blockade"], 4)

    def test_field_capture_reports_only_the_selected_opposing_pair(self):
        board = position({(3, 3): "K", (3, 2): "A", (0, 4): "A", (7, 7): "A"})
        f = capture_formation(board)
        self.assertEqual(f["axis"], "horizontal")
        self.assertEqual(f["missing"], [(3, 4)])
        self.assertEqual(f["reachable"], [(3, 4)])
        self.assertTrue(f["immediate_capture"])
        self.assertFalse(f["formation_complete"])

    def test_distant_capturable_blocker_is_unstable(self):
        board = position({(2, 2): "K", (2, 6): "A", (3, 6): "D", (1, 4): "D", (8, 8): "A"})
        details = control_details(board)
        self.assertIn((2, 6), details["key_blockers"])
        self.assertIn((2, 6), details["unstable_blockers"])

    def test_tactical_escape_checks_repetition_at_root(self):
        board = position({(2, 2): "K", (7, 6): "A", (8, 8): "A"})
        self.assertGreater(tactical_escape(board, 1), 0)
        self.assertEqual(tactical_escape(board, history=(get_state_key(board, "D"),)), 0)

    def test_strategy_bonus_is_zero_sum(self):
        evaluator = AttackerStrategyEvaluator(WeightedEvaluator((0,)*8), "A2")
        board = position({(3, 3): "K", (3, 2): "A", (0, 4): "A"})
        self.assertGreater(evaluator(board, "A"), 0)
        self.assertEqual(evaluator(board, "A"), -evaluator(board, "D"))

    def test_reachable_replay_rejects_false_outcome_and_moves_after_repetition(self):
        corpus = Path(__file__).resolve().parents[1] / "reports/external_analysis/corpus_merged166.jsonl"
        with corpus.open(encoding="utf-8") as records:
            row = next(row for row in map(json.loads, records) if row["termination"] == "repetition")
        self.assertTrue(validate(row)[0])
        self.assertFalse(validate(dict(row, winner="A"))[0])
        invalid = dict(row, moves=row["moves"]+[row["moves"][0]])
        self.assertIn("move after terminal", validate(invalid)[1])
