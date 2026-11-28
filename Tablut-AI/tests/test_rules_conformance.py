"""V7 Phase 1 (P0-1): the rules contract, checked against the course referee.

Each test states one rule fact in the terms of ``reference/Tablut.py`` and asserts that
``src/game.py`` reproduces the referee's board and verdict exactly. Nothing here is a
variant-rule assumption from other Hnefatafl sources.
"""
import contextlib
import io
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))
from Tablut import Tablut

from src.game import (apply_move, check_winner, get_legal_moves, get_state_key,
                      has_any_move, initial_board)


def board_with(pieces):
    board = [["."] * 9 for _ in range(9)]
    board[4][4] = "X"
    for (r, c), piece in pieces.items():
        board[r][c] = piece
    return tuple(map(tuple, board))


def referee(board):
    game = Tablut()
    game.board = [list(row) for row in board]
    game.past_positions = []
    return game


def referee_after(board, move, is_attacker):
    game = referee(board)
    ok = game.make_move(is_attacker, [list(move[0]), list(move[1])])
    return ok, tuple(map(tuple, game.board))


def referee_verdict(board, attacker_to_move):
    game = referee(board)
    with contextlib.redirect_stdout(io.StringIO()):
        over = game.check_if_game_over(attacker_to_move)
    return over, game.winner


class CaptureGeometryTests(unittest.TestCase):
    def assert_same_transition(self, board, move, is_attacker):
        side = "A" if is_attacker else "D"
        ok, expected = referee_after(board, move, is_attacker)
        self.assertTrue(ok, f"referee rejected {move}")
        actual = apply_move(board, move, side)
        if actual == expected:
            return
        # Documented deviation: after the king is captured *on the castle* the referee
        # writes '.' there while we keep 'X' so the castle invariant still holds.
        self.assertIsNone(next((piece for row in expected for piece in row if piece == "K"), None))
        normalised = tuple(tuple("X" if (r, c) == (4, 4) and piece == "." else piece
                                 for c, piece in enumerate(row)) for r, row in enumerate(expected))
        self.assertEqual(actual, normalised)

    def test_king_in_castle_needs_four_sides(self):
        three_sides = board_with({(4, 4): "K", (3, 4): "A", (5, 4): "A", (4, 3): "A",
                                  (0, 2): "A", (4, 7): "A"})
        # (0,2)->(4,2) reaches the king's row but not a fourth side: the king stays.
        self.assert_same_transition(three_sides, ((0, 2), (4, 2)), True)
        self.assertEqual(check_winner(apply_move(three_sides, ((0, 2), (4, 2)), "A"), "D"), None)
        # Sliding to (4, 5) completes the ring: the king is captured.
        completed = board_with({(4, 4): "K", (3, 4): "A", (5, 4): "A", (4, 3): "A",
                                (0, 2): "A", (4, 7): "A"})
        after = apply_move(completed, ((4, 7), (4, 5)), "A")
        self.assert_same_transition(completed, ((4, 7), (4, 5)), True)
        self.assertEqual(check_winner(after, "D"), "A")

    def test_king_beside_castle_needs_three_sides_plus_castle(self):
        two_sides = board_with({(4, 3): "K", (3, 3): "A", (5, 3): "A", (4, 0): "A"})
        # (4, 2) stays empty, so the ring is incomplete.
        self.assert_same_transition(two_sides, ((4, 0), (4, 1)), True)
        completed = board_with({(4, 3): "K", (3, 3): "A", (5, 3): "A", (4, 0): "A"})
        after = apply_move(completed, ((4, 0), (4, 2)), "A")
        self.assert_same_transition(completed, ((4, 0), (4, 2)), True)
        self.assertEqual(check_winner(after, "D"), "A")

    def test_normal_position_needs_two_opposing_attackers(self):
        board = board_with({(2, 2): "K", (2, 1): "A", (2, 6): "A"})
        after = apply_move(board, ((2, 6), (2, 3)), "A")
        self.assert_same_transition(board, ((2, 6), (2, 3)), True)
        self.assertEqual(check_winner(after, "D"), "A")
        # A single attacker cannot take the king in the open.
        one_side = board_with({(2, 2): "K", (2, 6): "A", (7, 7): "A"})
        self.assert_same_transition(one_side, ((2, 6), (2, 3)), True)
        self.assertEqual(check_winner(apply_move(one_side, ((2, 6), (2, 3)), "A"), "D"), None)

    def test_king_captures_an_attacker(self):
        board = board_with({(2, 0): "K", (2, 3): "A", (2, 4): "D"})
        after = apply_move(board, ((2, 0), (2, 2)), "D")
        self.assert_same_transition(board, ((2, 0), (2, 2)), False)
        self.assertEqual(after[2][3], ".")

    def test_defender_piece_is_captured_by_two_sided_pressure(self):
        board = board_with({(6, 6): "K", (2, 2): "A", (2, 3): "D", (2, 6): "A"})
        after = apply_move(board, ((2, 6), (2, 4)), "A")
        self.assert_same_transition(board, ((2, 6), (2, 4)), True)
        self.assertEqual(after[2][3], ".")

    def test_castle_counts_as_support_for_an_attacker_capture(self):
        # The empty castle (X) stands behind the defender, so the attacker may capture.
        board = board_with({(2, 2): "K", (4, 1): "A", (4, 3): "D"})
        after = apply_move(board, ((4, 1), (4, 2)), "A")
        self.assert_same_transition(board, ((4, 1), (4, 2)), True)
        self.assertEqual(after[4][3], ".")


class MovementRuleTests(unittest.TestCase):
    def test_castle_is_passable_but_never_a_destination(self):
        board = board_with({(4, 2): "A"})
        legal = get_legal_moves(board, "A")
        self.assertIn(((4, 2), (4, 6)), legal)
        self.assertNotIn(((4, 2), (4, 4)), legal)
        self.assertEqual(referee_after(board, ((4, 2), (4, 4)), True)[0], False)

    def test_king_cannot_return_to_the_castle(self):
        board = board_with({(4, 2): "K", (4, 6): "D", (0, 0): "A", (8, 8): "A"})
        self.assertNotIn(((4, 2), (4, 4)), get_legal_moves(board, "D"))
        self.assertEqual(referee_after(board, ((4, 2), (4, 4)), False)[0], False)

    def test_initial_position_gives_the_king_no_move(self):
        board = initial_board()
        self.assertEqual([m for m in get_legal_moves(board, "D") if m[0] == (4, 4)], [])
        self.assertTrue(has_any_move(board, "D"))

    def test_static_sandwich_changes_nothing_until_a_move_is_made(self):
        board = board_with({(2, 2): "K", (2, 1): "A", (2, 3): "A"})
        # A zero-length "move" is illegal and must not resolve any capture.
        with self.assertRaises(ValueError):
            apply_move(board, ((2, 1), (2, 1)), "A")
        self.assertEqual(board[2][1], "A")


class TerminalVerdictTests(unittest.TestCase):
    def test_attacker_with_one_piece_loses(self):
        board = board_with({(2, 2): "K", (2, 6): "A"})
        over, winner = referee_verdict(board, False)
        self.assertTrue(over)
        self.assertEqual(winner, "D")
        self.assertEqual(check_winner(board, "D"), "D")

    def test_king_on_the_edge_wins_for_the_defender(self):
        board = board_with({(0, 2): "K", (2, 6): "A", (6, 6): "A"})
        over, winner = referee_verdict(board, True)
        self.assertTrue(over)
        self.assertEqual(winner, "D")
        self.assertEqual(check_winner(board, "A"), "D")

    def test_full_blockade_is_a_draw_not_an_attacker_win(self):
        board = tuple(tuple("K" if (r, c) == (4, 4) else "A" for c in range(9)) for r in range(9))
        over, winner = referee_verdict(board, False)
        self.assertTrue(over)
        self.assertIsNone(winner)
        self.assertEqual(check_winner(board, "D"), "DRAW")

    def test_missing_king_is_an_attacker_win(self):
        board = board_with({(4, 3): "A", (2, 6): "A"})
        over, winner = referee_verdict(board, False)
        self.assertTrue(over)
        self.assertEqual(winner, "A")
        self.assertEqual(check_winner(board, "D"), "A")


class BlockadeAndRepetitionTests(unittest.TestCase):
    """Reachable-position tests for the blockade/draw rules (review item 3.5)."""

    def test_blocked_king_with_other_defender_moves_is_not_a_draw(self):
        # The king is boxed in, but a guard still has a legal move: the game goes on.
        board = board_with({(4, 4): "K", (3, 4): "A", (5, 4): "A", (4, 3): "A", (4, 5): "A",
                            (1, 1): "D", (2, 6): "A"})
        over, winner = referee_verdict(board, False)
        self.assertFalse(over)
        self.assertIsNone(winner)
        self.assertIsNone(check_winner(board, "D"))

    def test_blocked_king_and_no_defender_move_is_a_draw(self):
        board = board_with({(4, 4): "K", (3, 4): "A", (5, 4): "A", (4, 3): "A", (4, 5): "A",
                            (2, 6): "A"})
        over, winner = referee_verdict(board, False)
        self.assertTrue(over)
        self.assertIsNone(winner)
        self.assertEqual(check_winner(board, "D"), "DRAW")

    def test_repetition_needs_the_same_position_and_side_to_move(self):
        board = initial_board()
        key = get_state_key(board, "A")
        self.assertEqual(check_winner(board, "A", (key,)), "DRAW")
        self.assertIsNone(check_winner(board, "A", (get_state_key(board, "D"),)))

    def test_defender_can_open_its_own_corridor(self):
        # A guard steps aside and immediately gives the king a ray to the edge.
        board = board_with({(4, 4): "K", (4, 2): "D", (2, 2): "A", (2, 6): "A"})
        after = apply_move(board, ((4, 2), (4, 1)), "D")
        ok, expected = referee_after(board, ((4, 2), (4, 1)), False)
        self.assertTrue(ok)
        self.assertEqual(after, expected)
        self.assertIn(((4, 4), (4, 8)), get_legal_moves(after, "D"))

    def test_attacker_can_close_the_corridor_again(self):
        board = board_with({(4, 4): "K", (4, 2): "D", (2, 2): "A", (2, 6): "A"})
        after = apply_move(board, ((4, 2), (4, 1)), "D")
        self.assertIn(((4, 4), (4, 8)), get_legal_moves(after, "D"))
        blocked = apply_move(after, ((2, 6), (4, 6)), "A")
        ok, expected = referee_after(after, ((2, 6), (4, 6)), True)
        self.assertTrue(ok)
        self.assertEqual(blocked, expected)
        self.assertNotIn(((4, 4), (4, 8)), get_legal_moves(blocked, "D"))


if __name__ == "__main__":
    unittest.main()
