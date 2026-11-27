"""V5: transposition-table correctness across different history paths.

The table caches scores, so the risk is reusing a score computed under a different
repetition history. These tests compare cached and uncached searches on identical
boards with different histories, including real game lines that contain shuffles.
"""
import unittest
from math import inf
from random import Random

from config.experimental import SearchOptions
from src.enhanced_search import EnhancedSearch, evaluate
from src.game import (apply_move, check_winner, get_legal_moves, get_state_key,
                      initial_board)


def score(board, side, depth, history=(), capacity=20_000):
    options = SearchOptions(depth, capacity, True)
    stats = dict(nodes=0, cutoffs=0, tt_hint_hits=0)
    search = EnhancedSearch(side, inf, evaluate, options, stats)
    return search.visit(board, side, depth, -inf, inf, history)[0]


def game_lines(count=4, plies=22, seed=4242):
    """Yield (board, side, history) snapshots from real shuffled games."""
    rng = Random(seed)
    lines = []
    for _ in range(count):
        board, side, history = initial_board(), "A", []
        snapshots = [(board, side, tuple(history))]
        for _ in range(plies):
            moves = get_legal_moves(board, side)
            if not moves:
                break
            history.append(get_state_key(board, side))
            board = apply_move(board, rng.choice(moves), side)
            side = "D" if side == "A" else "A"
            snapshots.append((board, side, tuple(history)))
        lines.append(snapshots)
    return lines


class HistoryAwareCachingTests(unittest.TestCase):
    def test_unrelated_history_does_not_change_cached_scores(self):
        lines = game_lines(count=2, plies=16, seed=5)
        unrelated = [entry[0] for entry in lines[1][8:]]
        self.assertTrue(unrelated)
        for board, side, history in lines[0][::5]:
            if check_winner(board, side) is not None:
                continue
            clean = score(board, side, 2, ())
            for other in unrelated:
                key = get_state_key(other, "A")
                if key == get_state_key(board, side):
                    continue
                self.assertEqual(score(board, side, 2, (key,)), clean,
                                 "an unrelated history entry changed the score")

    def test_cached_and_plain_search_agree_along_real_game_lines(self):
        checked = 0
        for snapshots in game_lines(count=4, plies=22, seed=4242):
            for board, side, history in snapshots[4::4]:
                if check_winner(board, side, history) is not None:
                    continue
                cached = score(board, side, 3, history, capacity=20_000)
                plain = score(board, side, 3, history, capacity=0)
                self.assertEqual(cached, plain, f"cache changed the score for {side} history={len(history)}")
                checked += 1
        self.assertGreaterEqual(checked, 12)

    def test_repeated_root_is_a_draw_and_leaves_no_poisoned_entry(self):
        board = initial_board()
        key = get_state_key(board, "A")
        self.assertEqual(score(board, "A", 3, (key,)), 0.0)
        # The same board with a clean history must still produce the searched score.
        clean = score(board, "A", 3, ())
        self.assertNotEqual(clean, None)
        stats = dict(nodes=0, cutoffs=0, tt_hint_hits=0)
        search = EnhancedSearch("A", inf, evaluate, SearchOptions(3, 20_000, True), stats)
        search.visit(board, "A", 3, -inf, inf, ())
        self.assertEqual(search.visit(board, "A", 3, -inf, inf, (key,)), (0.0, ()))
        self.assertEqual(search.visit(board, "A", 3, -inf, inf, ())[0], clean)
        self.assertGreaterEqual(search.table.hits, 1)

    def test_deeper_search_is_not_poisoned_by_a_shallower_entry(self):
        board = initial_board()
        shallow = score(board, "A", 2, ())
        deep = score(board, "A", 3, ())
        # Warm the table with the shallow search, then ask for the deeper one again.
        stats = dict(nodes=0, cutoffs=0, tt_hint_hits=0)
        search = EnhancedSearch("A", inf, evaluate, SearchOptions(3, 20_000, True), stats)
        search.visit(board, "A", 2, -inf, inf, ())
        self.assertEqual(search.visit(board, "A", 3, -inf, inf, ())[0], deep)
        self.assertNotEqual(shallow, None)

    def test_proven_mate_survives_a_table_hit(self):
        board = [["."] * 9 for _ in range(9)]
        board[4][4] = "X"
        board[2][2] = "K"
        board[2][1] = "A"
        board[2][6] = "A"
        board = tuple(map(tuple, board))
        first = score(board, "A", 3, ())
        stats = dict(nodes=0, cutoffs=0, tt_hint_hits=0)
        search = EnhancedSearch("A", inf, evaluate, SearchOptions(3, 20_000, True), stats)
        search.visit(board, "A", 3, -inf, inf, ())
        again, pv = search.visit(board, "A", 3, -inf, inf, ())
        self.assertEqual(first, again)
        self.assertIn(pv[0], get_legal_moves(board, "A"))


if __name__ == "__main__":
    unittest.main()
