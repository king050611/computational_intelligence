import copy
import random
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))
from Tablut import Tablut
from TeamXX import Player
from src.game import initial_board, get_legal_moves, apply_move, check_winner, get_state_key
from src.search import choose_move, TimeManager
from src.evaluation import evaluate_attacker, evaluate_defender


def board_with(pieces):
    board = [["."]*9 for _ in range(9)]
    board[4][4] = "X"
    for (r,c), piece in pieces.items():
        board[r][c] = piece
    return tuple(map(tuple, board))


class BotTests(unittest.TestCase):
    def test_initial_and_key(self):
        board = initial_board()
        self.assertEqual(board, tuple(map(tuple, Tablut().board)))
        self.assertEqual([sum(row.count(p) for row in board) for p in "ADK"], [16,8,1])
        self.assertNotEqual(get_state_key(board,"A"), get_state_key(board,"D"))

    def test_castle_and_blocking(self):
        board = board_with({(4,2):"A", (4,7):"D"})
        moves = get_legal_moves(board,"A")
        self.assertIn(((4,2),(4,6)),moves)
        for end in ((4,4),(4,7),(4,8),(3,3),(4,2)):
            self.assertNotIn(((4,2),end),moves)
        with self.assertRaises(ValueError):
            apply_move(board,((4,2),(4,4)),"A")

    def test_all_initial_moves_match_official(self):
        for side in ("A","D"):
            game = Tablut()
            expected = set()
            for r in range(9):
                for c in range(9):
                    for nr in range(9):
                        for nc in range(9):
                            probe = copy.copy(game)
                            move = ((r,c),(nr,nc))
                            if probe.make_move(side == "A",move):
                                expected.add(move)
            self.assertEqual(set(get_legal_moves(game.board,side)),expected)

    def test_transitions_match_official_reachable_positions(self):
        rng, game = random.Random(17), Tablut()
        for ply in range(60):
            side = "A" if ply%2 == 0 else "D"
            moves = get_legal_moves(game.board,side)
            for move in moves:
                probe = copy.copy(game)
                self.assertTrue(probe.make_move(side=="A",move))
                self.assertEqual(apply_move(game.board,move,side),tuple(map(tuple,probe.board)))
            if not moves:
                break
            game.make_move(side=="A",rng.choice(moves))
            if game.check_if_game_over(side!="A"):
                break

    def test_simultaneous_capture_and_castle_support(self):
        board = board_with({(3,1):"A",(3,4):"D",(3,5):"A",(2,3):"D",(1,3):"A",(4,3):"D"})
        after = apply_move(board,((3,1),(3,3)),"A")
        self.assertEqual([after[3][4],after[2][3]], [".","."])
        board = board_with({(4,1):"A",(4,3):"D"})
        self.assertEqual(apply_move(board,((4,1),(4,2)),"A")[4][3],".")

    def test_king_capture_positions(self):
        cases = [
            ({(4,4):"K",(3,4):"A",(4,3):"A",(5,4):"A",(4,8):"A"},((4,8),(4,5)),(4,4)),
            ({(4,5):"K",(3,5):"A",(5,5):"A",(4,8):"A"},((4,8),(4,6)),(4,5)),
            ({(2,2):"K",(2,1):"A",(2,6):"A"},((2,6),(2,3)),(2,2)),
        ]
        for pieces,move,king in cases:
            after = apply_move(board_with(pieces),move,"A")
            self.assertNotEqual(after[king[0]][king[1]],"K")
            self.assertEqual(check_winner(after,"D"),"A")

    def test_special_defender_capture(self):
        board = board_with({(4,4):"K",(3,4):"A",(4,3):"A",(5,4):"A",(4,5):"D",(4,8):"A"})
        after = apply_move(board,((4,8),(4,6)),"A")
        self.assertEqual(after[4][5],".")
        self.assertEqual(after[4][4],"K")

    def test_terminal_conditions(self):
        board = board_with({(0,2):"K",(1,1):"A",(1,2):"A"})
        self.assertEqual(check_winner(board,"A"),"D")
        board = board_with({(4,4):"K",(1,1):"A"})
        self.assertEqual(check_winner(board,"A"),"D")
        board = initial_board()
        self.assertEqual(check_winner(board,"A",[get_state_key(board,"A")]),"DRAW")
        self.assertIsNone(check_winner(board,"A",[get_state_key(board,"D")]))
        blocked = tuple(tuple("K" if (r,c)==(4,4) else "A" for c in range(9)) for r in range(9))
        self.assertEqual(check_winner(blocked,"D"),"DRAW")

    def test_greedy_escape_and_capture(self):
        board = board_with({(2,2):"K",(2,1):"A",(2,6):"A"})
        move = choose_move(board,"D")
        self.assertEqual(check_winner(apply_move(board,move,"D"),"A"),"D")
        move = choose_move(board,"A")
        self.assertEqual(check_winner(apply_move(board,move,"A"),"D"),"A")

    def test_evaluation_changes(self):
        a = initial_board()
        b = board_with({(2,2):"K",(2,1):"A",(2,6):"A"})
        self.assertNotEqual(evaluate_attacker(a),evaluate_attacker(b))
        self.assertNotEqual(evaluate_defender(a),evaluate_defender(b))

    def test_budget_fallback_and_input_unchanged(self):
        clock = TimeManager()
        clock.record_elapsed(60)
        self.assertEqual(clock.allocate_time(),0)
        board = Tablut().board
        original = copy.deepcopy(board)
        self.assertIn(choose_move(board,"A",0),get_legal_moves(board,"A"))
        player = Player()
        for side,method in (("A",player.play_attacker),("D",player.play_defender)):
            move = method(board)
            self.assertTrue(all(isinstance(x,list) for x in move))
            self.assertIn(tuple(map(tuple,move)),get_legal_moves(board,side))
        self.assertEqual(board,original)
