"""V4 search primitives: legality parity, repetition-safe table, fixed node budget."""
import unittest
from math import inf
from random import Random
from unittest.mock import patch

from config.experimental import SearchOptions
from src.enhanced_search import EnhancedSearch, choose_enhanced, evaluate
from src.game import (apply_move, check_winner, get_legal_moves, get_piece_moves,
                      get_state_key, has_any_move, initial_board, is_legal_move)
from src.tactics import analyze


def positions(count=12, plies=18, seed=99):
    rng, board, side = Random(seed), initial_board(), "A"
    out = []
    for _ in range(count):
        for _ in range(rng.choice((0, 2, 6, 10))):
            moves = get_legal_moves(board, side)
            if not moves:
                break
            board = apply_move(board, rng.choice(moves), side)
            side = "D" if side == "A" else "A"
        out.append((board, side))
        for _ in range(plies):
            moves = get_legal_moves(board, side)
            if not moves:
                break
            board = apply_move(board, rng.choice(moves), side)
            side = "D" if side == "A" else "A"
    return out


def session(side, options=None, stats=None):
    return EnhancedSearch(side, inf, evaluate, options or SearchOptions(),
                          stats if stats is not None else dict(nodes=0, cutoffs=0, tt_hint_hits=0))


class LegalityParityTests(unittest.TestCase):
    def test_is_legal_move_matches_move_list(self):
        for board, side in positions():
            legal = set(get_legal_moves(board, side))
            for r in range(9):
                for c in range(9):
                    for nr in range(9):
                        for nc in range(9):
                            move = ((r, c), (nr, nc))
                            self.assertEqual(is_legal_move(board, move, side), move in legal,
                                             f"{side} {move} on {board}")

    def test_has_any_move_matches_move_generation(self):
        for board, side in positions():
            self.assertEqual(has_any_move(board, side), bool(get_legal_moves(board, side)))

    def test_piece_moves_are_a_subset_of_all_moves(self):
        for board, side in positions():
            legal = set(get_legal_moves(board, side))
            for r in range(9):
                for c in range(9):
                    for move in get_piece_moves(board, (r, c), side):
                        self.assertIn(move, legal)

    def test_castle_is_passable_but_not_a_destination(self):
        board = [["."] * 9 for _ in range(9)]
        board[4][4] = "X"
        board[4][2] = "A"
        board = tuple(map(tuple, board))
        self.assertIn(((4, 2), (4, 6)), get_legal_moves(board, "A"))
        self.assertFalse(is_legal_move(board, ((4, 2), (4, 4)), "A"))
        self.assertTrue(has_any_move(board, "A"))

    def test_stalemate_agrees_with_any_move_scan(self):
        board = tuple(tuple("K" if (r, c) == (4, 4) else "A" for c in range(9)) for r in range(9))
        self.assertFalse(has_any_move(board, "D"))
        self.assertEqual(check_winner(board, "D"), "DRAW")


class TranspositionTests(unittest.TestCase):
    def test_table_scores_match_plain_search(self):
        for index, (board, side) in enumerate(positions(8)):
            if check_winner(board, side) is not None:
                continue
            plain = SearchOptions(2, 0, False)
            cached = SearchOptions(2, 20_000, True)
            a, _ = session(side, plain).visit(board, side, 2, -inf, inf, ())
            b, pv = session(side, cached).visit(board, side, 2, -inf, inf, ())
            self.assertEqual(a, b, f"position {index} disagrees")
            self.assertIn(pv[0], get_legal_moves(board, side))

    def test_repetition_draw_is_never_cached(self):
        board = initial_board()
        key = get_state_key(board, "A")
        search = session("A", SearchOptions(2, 20_000, True))
        first, _ = search.visit(board, "A", 2, -inf, inf, ())
        self.assertEqual(search.visit(board, "A", 2, -inf, inf, (key,)), (0.0, ()))
        # A cache hit may shorten the PV, but the score must still be the searched one.
        score, pv = search.visit(board, "A", 2, -inf, inf, ())
        self.assertEqual(score, first)
        self.assertIn(pv[0], get_legal_moves(board, "A"))
        self.assertGreaterEqual(search.table.hits, 1)

    def test_bounds_hit_returns_a_legal_move(self):
        board = initial_board()
        search = session("A", SearchOptions(3, 20_000, True))
        search.visit(board, "A", 3, -inf, inf, ())
        score, pv = search.visit(board, "A", 3, -inf, inf, ())
        self.assertIn(pv[0], get_legal_moves(board, "A"))

    def test_table_is_bounded(self):
        search = session("A", SearchOptions(1, 4, True))
        for board, side in positions(10):
            search.visit(board, side, 1, -inf, inf, ())
        self.assertLessEqual(len(search.table.entries), 4)


class NodeBudgetTests(unittest.TestCase):
    def test_fixed_node_budget_is_deterministic(self):
        board = initial_board()
        options = SearchOptions(4, 20_000, True, node_budget=1500)
        runs = []
        for _ in range(2):
            stats = {}
            move = choose_enhanced(board, "A", deadline=inf, stats=stats, options=options)
            runs.append((move, stats["nodes"], stats["completed_depth"], stats["finish_reason"]))
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[0][1], 1501)
        self.assertTrue(runs[0][3] in ("search_deadline", "depth_completed"))

    def test_node_budget_reports_fallback(self):
        board = initial_board()
        stats = {}
        move = choose_enhanced(board, "A", deadline=inf, stats=stats,
                               options=SearchOptions(4, 20_000, True, node_budget=200))
        self.assertIn(move, get_legal_moves(board, "A"))
        self.assertGreaterEqual(stats["completed_depth"], 1)
        self.assertTrue(stats["fallback_used"])

    def test_tactical_scan_uses_a_work_bound_not_the_clock(self):
        board = initial_board()
        with patch("src.enhanced_search.perf_counter", return_value=1.0):
            info = analyze(board, "A", inf, (), max_nodes=5)
        self.assertFalse(info.status_complete)
        self.assertEqual(info.risk_level, "unknown")

    def test_deterministic_tactical_scan_in_node_mode(self):
        calls = {}
        board = initial_board()

        def spy(*args, **kwargs):
            calls["max_nodes"] = kwargs.get("max_nodes")
            return args[2], type("I", (), dict(status_complete=False, opponent_threat_now=None,
                                               immediate_wins=()))()

        with patch("src.enhanced_search.is_urgent", return_value=True), \
                patch("src.enhanced_search.prioritize", side_effect=spy):
            choose_enhanced(board, "A", deadline=inf, options=SearchOptions(1, 0, True, 500))
        self.assertEqual(calls["max_nodes"], 200)


if __name__ == "__main__":
    unittest.main()
