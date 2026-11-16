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
        move = choose_move(board,"D",strategy="greedy")
        self.assertEqual(check_winner(apply_move(board,move,"D"),"A"),"D")
        move = choose_move(board,"A",strategy="greedy")
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


class SearchV2Tests(unittest.TestCase):
    def test_pruned_scores_equal_exhaustive_for_both_root_views(self):
        from src.search import alpha_beta
        board = board_with({(2,2):"K",(2,1):"A",(6,6):"A",(3,2):"D"})
        scores=[]
        for root in ("A","D"):
            pruned, full = {}, {}
            a=alpha_beta(board,"A",root,2,-float("inf"),float("inf"),float("inf"),stats=pruned)
            b=alpha_beta(board,"A",root,2,-float("inf"),float("inf"),float("inf"),prune=False,stats=full)
            self.assertEqual(a,b)
            self.assertLessEqual(pruned["nodes"],full["nodes"])
            scores.append(a)
        self.assertLess(scores[0],0)
        self.assertGreater(scores[1],0)

    def test_path_repetition_is_a_draw(self):
        from src.search import alpha_beta
        board=initial_board()
        self.assertEqual(alpha_beta(board,"A","A",2,-float("inf"),float("inf"),float("inf"),
                                    (get_state_key(board,"A"),)),0)

    def test_fixed_minimax_blocks_escape(self):
        board=board_with({(1,2):"K",(0,2):"A",(1,0):"A",(2,2):"A",(4,8):"A"})
        stats={}
        move=choose_move(board,"A",strategy="minimax",stats=stats)
        after=apply_move(board,move,"A")
        self.assertEqual(stats["completed_depth"],2)
        self.assertFalse(any(check_winner(apply_move(after,m,"D"),"A")=="D"
                             for m in get_legal_moves(after,"D")))

    def test_timeout_keeps_last_completed_iteration(self):
        from unittest.mock import patch
        from src.search import SearchTimeout
        board=initial_board()
        greedy=choose_move(board,"A",strategy="greedy")
        stats={}
        with patch("src.search.alpha_beta",side_effect=SearchTimeout):
            move=choose_move(board,"A",strategy="adaptive",stats=stats)
        self.assertEqual(move,greedy)
        self.assertEqual(stats["completed_depth"],1)
        self.assertTrue(stats["timed_out"])
        stats={}
        self.assertIn(choose_move(board,"A",0,stats=stats),get_legal_moves(board,"A"))
        self.assertEqual(stats["completed_depth"],0)

    def test_recursive_deadline_and_immediate_win(self):
        from src.search import alpha_beta, SearchTimeout
        with self.assertRaises(SearchTimeout):
            alpha_beta(initial_board(),"A","A",3,-float("inf"),float("inf"),0)
        board=board_with({(2,2):"K",(2,1):"A",(2,6):"A"})
        for strategy in ("greedy","minimax","adaptive"):
            for side in ("A","D"):
                move=choose_move(board,side,strategy=strategy)
                self.assertEqual(check_winner(apply_move(board,move,side),"D" if side=="A" else "A"),side)

    def test_adaptive_depth_policy(self):
        from unittest.mock import patch
        from src.search import is_urgent
        board=initial_board()
        self.assertFalse(is_urgent(board))
        stats={}
        # Control only scoring to inspect the policy without a large depth-3 tree.
        with patch("src.search.is_urgent",return_value=True), patch("src.search.DEEP_SEARCH_MAX_BRANCHES",1000), patch("src.search.alpha_beta",return_value=1):
            choose_move(board,"A",strategy="adaptive",stats=stats)
        self.assertEqual(stats["target_depth"],3)
        self.assertEqual(stats["completed_depth"],3)


class BattleV2Tests(unittest.TestCase):
    def test_scores_and_roles(self):
        from scripts.benchmark import standings
        table=standings([dict(our_side="A",winner="A"),dict(our_side="D",winner="DRAW"),dict(our_side="A",winner="D")])
        self.assertEqual(table["overall"],dict(games=3,wins=1,draws=1,losses=1,points=3))
        self.assertEqual(table["defender"]["points"],1)

    def test_external_dependencies_are_isolated_and_instances_fresh(self):
        import tempfile
        from scripts.benchmark import ExternalBot
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"src").mkdir()
            (root/"src/__init__.py").write_text("")
            (root/"src/helper.py").write_text("MOVE = [[0,3],[0,2]]")
            bot=root/"TeamYY.py"
            bot.write_text("from src.helper import MOVE\nclass Player:\n def __init__(self): self.calls=0\n def play_attacker(self,board):\n  self.calls+=1\n  return MOVE if self.calls==1 else [[0,3],[0,1]]\n def play_defender(self,board): return MOVE\n")
            for _ in range(2):
                external=ExternalBot(bot)
                try:
                    self.assertEqual(external.play_attacker(Tablut().board),[[0,3],[0,2]])
                finally:
                    external.close()
            from src.game import initial_board
            self.assertEqual(initial_board()[4][4],"K")


class BattleFailureTests(unittest.TestCase):
    def test_bad_moves_and_exceptions_are_recorded_by_referee(self):
        import contextlib
        import io
        from scripts.benchmark import Timed
        class Bad:
            def play_attacker(self,board): return None
            def play_defender(self,board): raise RuntimeError("fixture failure")
        for bad_is_attacker in (True,False):
            bad, good = Timed(Bad()), Timed(Player())
            game=Tablut()
            with contextlib.redirect_stdout(io.StringIO()) as log:
                game.play(bad,good) if bad_is_attacker else game.play(good,bad)
            self.assertEqual(game.winner,"D" if bad_is_attacker else "A")
            if bad_is_attacker:
                self.assertEqual(bad.invalid_returns,["None"])
                self.assertIn("Illegal move",log.getvalue())
            else:
                self.assertEqual(bad.errors[0]["message"],"fixture failure")
                self.assertIn("Exception caught",log.getvalue())

    def test_unfinished_depth_three_preserves_depth_two(self):
        from unittest.mock import patch
        from src.search import SearchTimeout
        def controlled(board,current,root,depth,*args,**kwargs):
            if depth==2:
                raise SearchTimeout()
            return 1
        stats={}
        with patch("src.search.is_urgent",return_value=True), patch("src.search.DEEP_SEARCH_MAX_BRANCHES",1000), patch("src.search.alpha_beta",side_effect=controlled):
            move=choose_move(initial_board(),"A",stats=stats)
        self.assertIn(move,get_legal_moves(initial_board(),"A"))
        self.assertEqual(stats["completed_depth"],2)
        self.assertTrue(stats["timed_out"])
