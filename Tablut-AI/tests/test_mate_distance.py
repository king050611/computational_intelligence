"""V5-B: mate distance (WIN_SCORE - ply) and its transposition-table normalisation."""
import unittest
from math import inf

from config.experimental import SearchOptions
from src.enhanced_search import EnhancedSearch, choose_enhanced, evaluate
from src.game import apply_move, check_winner, get_legal_moves
from src.transposition import MATE_BOUND, MATE_SCORE, from_table, to_table


def position(pieces):
    board = [["."] * 9 for _ in range(9)]
    board[4][4] = "X"
    for (r, c), piece in pieces.items():
        board[r][c] = piece
    return tuple(map(tuple, board))


def session(side, depth, capacity=20_000):
    stats = dict(nodes=0, cutoffs=0, tt_hint_hits=0)
    return EnhancedSearch(side, inf, evaluate, SearchOptions(depth, capacity, True), stats), stats


class MateDistanceTests(unittest.TestCase):
    def test_table_conversion_round_trips(self):
        win = MATE_SCORE - 5
        loss = -MATE_SCORE + 5
        self.assertEqual(from_table(to_table(win, 3), 3), win)
        self.assertEqual(to_table(win, 3), win + 3)
        self.assertEqual(from_table(win + 3, 3), win)
        self.assertEqual(to_table(loss, 4), loss - 4)
        self.assertEqual(from_table(loss - 4, 4), loss)
        self.assertEqual(to_table(12.5, 7), 12.5)
        self.assertEqual(from_table(-12.5, 7), -12.5)

    def test_table_keeps_the_mate_distance_across_plies(self):
        board = position({(2, 2): "K", (2, 1): "A", (2, 6): "A"})
        search, _ = session("A", 2)
        from src.game import get_state_key
        key = get_state_key(board, "A")
        search.table.store(key, 2, MATE_SCORE - 4, 0, ((2, 6), (2, 3)), ply=2)
        # At the root (ply 0) the same entry must look one ply further from the mate.
        self.assertEqual(search.table.probe(key, 2, -inf, inf, 0), MATE_SCORE - 2)

    def test_tactical_win_reports_mate_in_one(self):
        board = position({(2, 2): "K", (2, 1): "A", (2, 6): "A"})
        stats = {}
        move = choose_enhanced(board, "A", deadline=inf, stats=stats, options=SearchOptions(3))
        self.assertEqual(stats["finish_reason"], "tactical_win")
        self.assertEqual(stats["score"], MATE_SCORE - 1)
        self.assertEqual(check_winner(apply_move(board, move, "A"), "D"), "A")

    def test_mate_distance_is_stable_across_search_depths(self):
        board = position({(2, 2): "K", (2, 1): "A", (2, 6): "A"})
        for depth in (1, 2, 3):
            search, _ = session("A", depth)
            score, pv = search.visit(board, "A", depth, -inf, inf, ())
            self.assertGreaterEqual(score, MATE_BOUND)
            self.assertEqual(score, MATE_SCORE - 1, f"depth {depth} lost the mate distance")
            self.assertEqual(check_winner(apply_move(board, pv[0], "A"), "D"), "A")

    def test_cached_mate_search_matches_plain(self):
        board = position({(2, 2): "K", (2, 1): "A", (2, 6): "A"})
        for depth in (2, 3):
            cached, _ = session("A", depth, 20_000)
            plain, _ = session("A", depth, 0)
            self.assertEqual(cached.visit(board, "A", depth, -inf, inf, ()),
                             plain.visit(board, "A", depth, -inf, inf, ()))

    def test_losing_terminal_is_scored_by_distance(self):
        # King already captured: the side to move has lost, and the score must shrink
        # with the number of plies already played (longer defence is better).
        board = position({(2, 1): "A", (2, 6): "A"})
        search, _ = session("D", 2)
        self.assertEqual(search.visit(board, "D", 2, -inf, inf, (), ply=1)[0], -(MATE_SCORE - 1))
        self.assertEqual(search.visit(board, "D", 2, -inf, inf, (), ply=3)[0], -(MATE_SCORE - 3))


if __name__ == "__main__":
    unittest.main()
