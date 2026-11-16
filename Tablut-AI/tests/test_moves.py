import copy
import unittest
from Tablut import Tablut
from src.core.state import GameState, initial_state, get_state_key
from src.core.move_generator import get_legal_moves, is_legal_move


class MoveTests(unittest.TestCase):
    def test_initial_counts_and_official_board(self):
        state = initial_state()
        self.assertEqual(state.board, tuple(map(tuple, Tablut().board)))
        cells = sum(state.board, ())
        self.assertEqual([cells.count(p) for p in "ADK"], [16, 8, 1])

    def test_turn_is_part_of_key(self):
        state = initial_state()
        self.assertNotEqual(get_state_key(state), get_state_key(GameState(state.board, "D")))

    def test_exact_move_set_matches_official_framework(self):
        for player in ("A", "D"):
            game = Tablut()
            state = GameState(game.board, player)
            expected = set()
            for r in range(9):
                for c in range(9):
                    for nr in range(9):
                        for nc in range(9):
                            probe = copy.copy(game)
                            if probe.make_move(player == "A", [[r,c],[nr,nc]]):
                                expected.add(((r,c),(nr,nc)))
            self.assertEqual(set(get_legal_moves(state)), expected)

    def test_castle_crossing_and_blocking(self):
        board = [["."] * 9 for _ in range(9)]
        board[4][4] = "X"
        board[4][2] = "A"
        board[4][7] = "D"
        state = GameState(board)
        self.assertTrue(is_legal_move(state, ((4,2),(4,6))))
        for end in ((4,4),(4,7),(4,8),(3,3),(4,2)):
            self.assertFalse(is_legal_move(state, ((4,2),end)))
