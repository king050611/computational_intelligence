import copy
import random
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))
from Tablut import Tablut
from TeamXX import Player
from src.game import initial_board, get_legal_moves, apply_move, check_winner, get_state_key
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

    def test_evaluation_changes(self):
        a = initial_board()
        b = board_with({(2,2):"K",(2,1):"A",(2,6):"A"})
        self.assertNotEqual(evaluate_attacker(a),evaluate_attacker(b))
        self.assertNotEqual(evaluate_defender(a),evaluate_defender(b))

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

class ReplayCleanupTests(unittest.TestCase):
    def test_observer_uses_public_side_methods_and_preserves_stats(self):
        from unittest.mock import patch
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
        from replay_demo import ObservedPlayer, Recorder
        class Stub:
            last_search_stats = {"nodes": 7}
        bot=Stub()
        for side,method,move in (("A","play_attacker",[[0,3],[0,2]]),
                                 ("D","play_defender",[[2,4],[2,3]])):
            with self.subTest(side=side):
                recorder=Recorder()
                observed=ObservedPlayer(bot,recorder,"first")
                with patch.object(observed.timed,method,return_value=move) as public_method, \
                     patch.object(observed.timed,"_play",side_effect=AssertionError("Private dispatch used")):
                    self.assertEqual(getattr(observed,method)(recorder.board),move)
                public_method.assert_called_once_with(recorder.board)
                self.assertEqual(recorder.pending["player"],side)
                self.assertEqual(recorder.pending["search"],bot.last_search_stats)
                self.assertIsNot(recorder.pending["search"],bot.last_search_stats)
                self.assertEqual(recorder.pending["move"],move)

    def test_full_replay_navigation_draw_and_cached_totals(self):
        import json, shutil, subprocess
        if not shutil.which("node"):
            self.skipTest("Node needed for HTML JavaScript test")
        def fixture(board,actions,winner,reason,monitoring):
            initial=[list(row) for row in board]
            events=[]
            for i,(side,move) in enumerate(actions):
                before=[list(row) for row in board]
                board=apply_move(board,move,side)
                event=dict(ply=i+1,player=side,piece=before[move[0][0]][move[0][1]],
                           strategy="first",from_square=list(move[0]),to_square=list(move[1]),
                           accepted=True,captures=[],elapsed_seconds=0.001,
                           board_before=before,board_after=[list(row) for row in board],
                           result_after=dict(terminal=i==len(actions)-1))
                if monitoring:
                    event["search"]=dict(strategy="first",completed_depth=0,nodes=0)
                events.append(event)
            return dict(game=1,our_side="A",initial_board=initial,moves=events,
                        result=dict(winner=winner,reason=reason),accepted_moves=len(events),
                        strategies=dict(A="first",D="first"))
        win=fixture(board_with({(2,2):"K",(2,1):"A",(2,6):"A"}),
                    [("A",((2,6),(2,3)))],"A","king_captured",True)
        draw=fixture(initial_board(),[("A",((0,3),(0,2))),("D",((2,4),(2,3))),
                                      ("A",((0,2),(0,3))),("D",((2,3),(2,4)))],
                     "DRAW","repetition",False)
        page=(Path(__file__).resolve().parents[1]/"scripts/replay_template.html").read_text(encoding="utf-8-sig")
        code=page.split("<script>")[1].split("</script>")[0]
        # Wrap the page's real aggregation function before its first load.
        pos=code.rfind("load();")
        code=code[:pos]+"const aggregate=totalsText;let calls=0;totalsText=g=>{calls++;return aggregate(g)};"+code[pos:]
        dom=r"""
    const assert=require('assert');
    class Element {
     constructor(){this.children=[];this.dataset={};this.classList={toggle(){}};this.value=0;this.checked=false;this.open=false;this.textContent=''}
     setAttribute(){} append(...nodes){this.children.push(...nodes)}
     replaceChildren(...nodes){this.children=nodes} scrollIntoView(){}
    }
    const elements={};
    global.document={getElementById:id=>elements[id]??=(new Element()),
     createElement:()=>new Element(),createElementNS:()=>new Element(),addEventListener(){}};
    let tick=null;
    global.setInterval=fn=>{tick=fn;return 1};global.clearInterval=()=>{tick=null};
    """
        checks=r"""
    assert.equal(calls,1);assert($('summary').textContent.includes('进攻方获胜'));
    assert($('analysis').textContent.includes('初始局面'));
    // Observe which snapshot the actual navigation passes into the renderer.
    diagram=(board,event)=>({board,event});
    $('next').onclick();assert.equal(step,1);
    assert.deepEqual($('board').children[0].board,data.games[0].moves[0].board_after);
    assert($('analysis').textContent.includes('first'));assert.equal(calls,1);
    $('before').checked=true;$('before').onchange();
    assert.deepEqual($('board').children[0].board,data.games[0].moves[0].board_before);
    $('first').onclick();assert.equal(step,0);assert.equal(calls,1);
    $('game').value=1;$('game').onchange();assert.equal(calls,2);
    assert($('summary').textContent.includes('平局'));assert(!$('summary').textContent.includes('平局获胜'));
    assert($('summary').textContent.includes('重复局面'));
    $('before').checked=false;$('last').onclick();assert.equal(step,4);
    assert($('analysis').textContent.includes('未记录'));assert.equal(calls,2);
    $('prev').onclick();assert.equal(step,3);
    $('slider').value=2;$('slider').oninput();assert.equal(step,2);
    $('moves').children[1].onclick();assert.equal(step,1);
    $('all').open=true;$('all').ontoggle();assert.equal($('gallery').children.length,5);
    $('gallery').children[4].onclick();assert.equal(step,4);assert.equal(calls,2);
    $('play').onclick();assert.equal(step,0);assert.equal(typeof tick,'function');
    for(let i=0;i<4;i++)tick();assert.equal(step,4);assert.equal(tick,null);
    assert.equal(calls,2);
    $('game').value=0;$('game').onchange();assert.equal(calls,3);assert.equal(step,0);
    assert.equal($('gallery').children.length,2);
    """
        program=dom+"document.getElementById('data').textContent="+json.dumps(json.dumps(dict(games=[win,draw])))+";\n"+code+checks
        subprocess.run(["node","-"],input=program,text=True,encoding="utf-8",check=True)
