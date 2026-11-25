from math import inf
import unittest
from unittest.mock import patch

from config.experimental import SearchOptions
from scripts.generate_openings import generate_openings
from scripts.run_experiments import summarize
from src.enhanced_search import EnhancedSearch, choose_enhanced, evaluate
from src.game import apply_move, check_winner, get_legal_moves, get_state_key, initial_board
from src.enhanced_search import SearchTimeout, WIN_SCORE
from tests.oracle import exact_score
from src.tactics import analyze
from src.time_control import AdaptiveTimeManager
from src.transposition import MoveHints


def position(pieces):
    board = [["."] * 9 for _ in range(9)]
    board[4][4] = "X"
    for (r, c), piece in pieces.items():
        board[r][c] = piece
    return tuple(map(tuple, board))


def session(side, options=None):
    return EnhancedSearch(side, inf, evaluate, options or SearchOptions(),
                          dict(nodes=0, cutoffs=0, tt_hint_hits=0))


class EnhancedSearchTests(unittest.TestCase):
    def test_fixed_score_and_best_move_for_both_roles(self):
        boards = [initial_board(), position({(2, 2): "K", (2, 1): "A", (6, 6): "A", (3, 2): "D"})]
        for board in boards:
            for side in ("A", "D"):
                with self.subTest(side=side, board=board):
                    score, pv = session(side).visit(board, side, 2, -inf, inf, ())
                    other = "D" if side == "A" else "A"
                    path = (get_state_key(board, side),)
                    exact = {move: exact_score(apply_move(board, move, side), other, side, 1, path)
                             for move in get_legal_moves(board, side)}
                    self.assertEqual(score, max(exact.values()))
                    self.assertEqual(exact[pv[0]], score)

    def test_hint_never_reuses_score_with_a_different_history(self):
        board = initial_board()
        key = get_state_key(board, "A")
        search = session("A")
        search.visit(board, "A", 2, -inf, inf, ())
        self.assertIsNotNone(search.hints.get(key))
        self.assertEqual(search.visit(board, "A", 2, -inf, inf, (key,)), (0, ()))
        self.assertEqual(search.visit(board, "A", 2, -inf, inf, (get_state_key(board, "D"),))[0],
                         exact_score(board, "A", "A", 2))

    def test_completed_layer_survives_timeout(self):
        board = initial_board()
        expected = choose_enhanced(board, "A", deadline=inf, options=SearchOptions(1))
        original = EnhancedSearch.visit

        def abort_second_layer(search, board, side, depth, *args, **kwargs):
            if depth == 2:
                raise SearchTimeout
            return original(search, board, side, depth, *args, **kwargs)

        stats = {}
        with patch.object(EnhancedSearch, "visit", abort_second_layer):
            self.assertEqual(choose_enhanced(board, "A", deadline=inf, stats=stats), expected)
        self.assertEqual(stats["completed_depth"], 1)
        self.assertEqual(stats["finish_reason"], "search_deadline")
        self.assertTrue(stats["fallback_used"])
        with patch("src.enhanced_search.perf_counter", return_value=5):
            move = choose_enhanced(board, "A", deadline=5, stats=stats)
        self.assertEqual(move, get_legal_moves(board, "A")[0])
        self.assertEqual(stats["completed_depth"], 0)
        with patch("src.enhanced_search.perf_counter", return_value=5):
            self.assertEqual(choose_enhanced(board, "A", deadline=6, soft_deadline=5, stats=stats), move)
        self.assertFalse(stats["timed_out"])
        self.assertEqual(stats["finish_reason"], "soft_deadline")

    def test_king_capture_and_escape_are_exact_wins(self):
        board = position({(2, 2): "K", (2, 1): "A", (2, 6): "A"})
        for side, other in (("A", "D"), ("D", "A")):
            stats = {}
            move = choose_enhanced(board, side, deadline=inf, stats=stats)
            self.assertEqual(check_winner(apply_move(board, move, side), other), side)
            self.assertEqual(stats["score"], WIN_SCORE)

    def test_hints_are_bounded_and_keep_deeper_entries(self):
        hints = MoveHints(1)
        hints.put("old", 3, "first")
        hints.put("old", 2, "second")
        self.assertEqual(hints.get("old"), "first")
        hints.put("new", 1, "third")
        self.assertIsNone(hints.get("old"))
        self.assertEqual(hints.get("new"), "third")


class TimeTacticsExperimentTests(unittest.TestCase):
    def test_bootstrap_resamples_openings_as_pairs(self):
        games = [dict(opening_id=opening, our_side=side, points=points)
                 for opening, points in ((1, 2), (2, 0)) for side in ("A", "D")]
        result = summarize({"results": games}, seed=42, samples=500)
        self.assertEqual(result["point_rate"], 0.5)
        self.assertEqual(result["ci95"], [0, 1])
        with self.assertRaises(ValueError):
            summarize({"results": games[:-1]})

    def test_dynamic_budget_caps_and_zero_budget(self):
        clock = AdaptiveTimeManager()
        soft, hard = clock.deadlines(10, 1.6)
        self.assertAlmostEqual(soft - 10, 0.8 * (hard - 10))
        self.assertLessEqual(hard - 10, 4)
        self.assertLess(clock.deadlines(10, 0.6)[1], hard)
        clock.record_elapsed(54)
        self.assertLessEqual(clock.deadlines(10, 1.6)[1] - 10, 0.200001)
        clock.record_elapsed(2)
        self.assertEqual(clock.deadlines(20), (20, 20))
        self.assertEqual(clock.turns, 2)

    def test_tactical_confirmation_and_unknown(self):
        board = position({(2, 2): "K", (2, 1): "A", (2, 6): "A"})
        self.assertIn(((2, 6), (2, 3)), analyze(board, "A", inf).immediate_wins)
        with patch("src.tactics.perf_counter", return_value=10):
            info = analyze(board, "A", 10)
        self.assertFalse(info.status_complete)
        self.assertEqual(info.risk_level, "unknown")

    def test_confirmed_defense_and_no_safe_reply(self):
        board = position({(1, 2): "K", (2, 2): "A", (2, 0): "A",
                          (2, 8): "A", (0, 2): "A", (1, 8): "D"})
        info = analyze(board, "A", inf)
        self.assertTrue(info.status_complete)
        self.assertTrue(info.opponent_threat_now)
        self.assertIn(((2, 0), (1, 0)), info.safe_replies)
        self.assertNotIn(((2, 0), (3, 0)), info.safe_replies)

        board = position({(2, 2): "K", (6, 6): "A", (7, 7): "A"})
        info = analyze(board, "A", inf)
        self.assertTrue(info.status_complete)
        self.assertTrue(info.opponent_threat_now)
        self.assertEqual(info.safe_replies, ())

    def test_seeded_openings_replay_without_terminal_states(self):
        data = generate_openings(6, 42)
        self.assertEqual(data, generate_openings(6, 42))
        self.assertEqual(len({entry["board"] for entry in data["openings"]}), 6)
        for entry in data["openings"]:
            board, history, side = initial_board(), [], "A"
            for move in entry["moves"]:
                history.append(get_state_key(board, side))
                board = apply_move(board, move, side)
                side = "D" if side == "A" else "A"
                self.assertIsNone(check_winner(board, side, history))
            self.assertEqual((board, side), (entry["board"], "A"))
