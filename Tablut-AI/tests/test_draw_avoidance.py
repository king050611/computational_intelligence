"""V5-A: pointless repetition is a tie-break, never a ban."""
import unittest
from math import inf

from config.experimental import SearchOptions
from src.enhanced_search import EnhancedSearch, choose_enhanced
from src.game import apply_move, get_legal_moves, get_state_key, initial_board


def constant_evaluator(board, side):
    """Every non-terminal line scores 0, so ordering alone decides the move."""
    return 0.0


def draw_moves(board, side, history):
    other = "D" if side == "A" else "A"
    return {move for move in get_legal_moves(board, side)
            if get_state_key(apply_move(board, move, side), other) in history}


class DrawAvoidanceTests(unittest.TestCase):
    def test_order_demotes_immediate_draws_at_the_root(self):
        board = initial_board()
        moves = get_legal_moves(board, "A")
        draw = moves[0]
        stats = dict(nodes=0, cutoffs=0, tt_hint_hits=0)
        search = EnhancedSearch("A", inf, constant_evaluator, SearchOptions(2, 20_000, True), stats)
        search.root_draw_moves = {draw}
        ordered = search.order(board, "A", moves, 0)
        self.assertEqual(ordered[-1], draw)
        self.assertEqual(set(ordered), set(moves))

    def test_draw_flag_is_ignored_below_the_root(self):
        board = initial_board()
        moves = get_legal_moves(board, "A")
        stats = dict(nodes=0, cutoffs=0, tt_hint_hits=0)
        search = EnhancedSearch("A", inf, constant_evaluator, SearchOptions(2, 20_000, True), stats)
        search.root_draw_moves = {moves[0]}
        ordered = search.order(board, "A", moves, 1)
        self.assertEqual(ordered[0], moves[0])

    def test_equal_scores_prefer_a_non_repeating_move(self):
        board = initial_board()
        moves = get_legal_moves(board, "A")
        repeating = moves[0]
        history = (get_state_key(apply_move(board, repeating, "A"), "D"),)
        stats = {}
        move = choose_enhanced(board, "A", deadline=inf, history=history, stats=stats,
                               evaluator=constant_evaluator, options=SearchOptions(2))
        self.assertIn(move, moves)
        self.assertNotEqual(move, repeating)
        self.assertEqual(stats["root_draw_moves"], 1)

    def test_no_history_means_no_draw_bookkeeping(self):
        board = initial_board()
        stats = {}
        move = choose_enhanced(board, "A", deadline=inf, stats=stats,
                               evaluator=constant_evaluator, options=SearchOptions(2))
        self.assertIn(move, get_legal_moves(board, "A"))
        self.assertNotIn("root_draw_moves", stats)

    def test_every_move_repeating_still_returns_a_legal_move(self):
        board = initial_board()
        other = "D"
        history = tuple(
            get_state_key(apply_move(board, move, "A"), other)
            for move in get_legal_moves(board, "A"))
        stats = {}
        move = choose_enhanced(board, "A", deadline=inf, history=history, stats=stats,
                               evaluator=constant_evaluator, options=SearchOptions(2))
        self.assertIn(move, get_legal_moves(board, "A"))
        self.assertEqual(stats["root_draw_moves"], stats["root_moves"])

    def test_a_repetition_can_still_be_the_best_scoring_choice(self):
        """When the repetition is the only move that is not losing, it must stay playable."""
        board = initial_board()
        moves = get_legal_moves(board, "A")
        repeating = moves[0]

        def evaluator(position, side):
            return 0.0

        history = (get_state_key(apply_move(board, repeating, "A"), "D"),)
        stats = {}
        # Constant evaluation: the repeating move ties with everything, so it is only
        # demoted, not removed -- the returned move must still be legal.
        move = choose_enhanced(board, "A", deadline=inf, history=history, stats=stats,
                               evaluator=evaluator, options=SearchOptions(1))
        self.assertIn(move, moves)


if __name__ == "__main__":
    unittest.main()
