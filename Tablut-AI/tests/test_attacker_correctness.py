"""Regressions run in the real attacker's isolated import environment."""
from pathlib import Path
import subprocess
import sys
import unittest


class AttackerCorrectnessTests(unittest.TestCase):
    def test_attack_engine_against_rule_oracle(self):
        engine = Path(__file__).resolve().parents[1] / "engines/attacker"
        program = r"""
import random, sys
from time import perf_counter
sys.path.insert(0,sys.argv[1])
from src.game import apply_move, check_winner, get_legal_moves, get_state_key, initial_board
from src.tactics import _gap_reachable, find_capture_moves, prove_capture, structure_state
from src.features import king_escape_distance, immediate_king_threat
from config.experimental import SearchOptions
from src.enhanced_search import choose_enhanced
from src.transposition import EXACT, TranspositionTable

def board(pieces):
    rows=[list(".........") for _ in range(9)]
    rows[4][4]="X"
    for (r,c), piece in pieces.items():
        rows[r][c]=piece
    return tuple(map(tuple, rows))

def oracle(state, history=()):
    if check_winner(state,"A",history) is not None:
        return set()
    path=(*history,get_state_key(state,"A"))
    return {move for move in get_legal_moves(state,"A")
            if check_winner(apply_move(state,move,"A"),"D",path)=="A"}

ray=board({(4,0):"A",(4,8):"A",(1,1):"K",(1,3):"D"})
assert set(_gap_reachable(ray,(4,6)))=={(4,0),(4,8)}
assert king_escape_distance(initial_board(),(4,4))==1.0
assert king_escape_distance(ray,(1,1))==.125
field=board({(3,3):"K",(3,2):"A",(0,4):"A",(6,3):"A"})
mate=((0,4),(3,4))
assert set(find_capture_moves(field))==oracle(field)=={mate}
assert immediate_king_threat(field,(3,3))==1.0
axes={p["axis"]:p for p in structure_state(field)["structures"]}
assert axes["horizontal"]["gaps"]==((3,4),) and axes["horizontal"]["origins"][(3,4)]==((0,4),)
assert axes["vertical"]["support"]==()
assert find_capture_moves(field,[get_state_key(field,"A")])==[]
end=apply_move(field,mate,"A")
assert find_capture_moves(field,[get_state_key(end,"D")])==[mate]
for seed in range(3):
    rng=random.Random(seed)
    position, side, history = initial_board(), "A", []
    for _ in range(45):
        if check_winner(position,side,history) is not None:
            break
        if side=="A":
            assert set(find_capture_moves(position,history))==oracle(position,history)
        history.append(get_state_key(position,side))
        position=apply_move(position,rng.choice(get_legal_moves(position,side)),side)
        side="D" if side=="A" else "A"

for center, pieces in (
    ((4,4),{(3,4):"A",(4,3):"A",(4,5):"A",(7,4):"A"}),
    ((4,3),{(3,3):"A",(4,2):"A",(1,3):"A",(5,0):"A"}),
):
    state=board(dict(pieces)|{center:"K"})
    assert set(find_capture_moves(state))==oracle(state)

proof=prove_capture(field,deadline=perf_counter()+1,moves=[mate])
assert proof.status=="WIN" and proof.line==(mate,)
limited=prove_capture(field,deadline=perf_counter()+1,max_nodes=0)
assert limited.status=="UNKNOWN" and limited.nodes==0
trap=tuple(map(tuple,(".........",".A.A.....","..A.A....",".D.K.A...",
                     "..ADXA...","...A.....",".........",".........",".........")))
assert not oracle(trap)
proof=prove_capture(trap,deadline=float("inf"))
assert proof.status=="WIN" and len(proof.line)==3
strike=proof.line[0]
stats={}
selected=choose_enhanced(trap,"A",deadline=perf_counter()+3,stats=stats,
                         options=SearchOptions(capture_proof=True))
assert selected==strike and stats["finish_reason"]=="capture_proof"
after=apply_move(trap,strike,"A")
replies=get_legal_moves(after,"D")
branch=(get_state_key(trap,"A"),get_state_key(after,"D"))
assert replies and all(oracle(apply_move(after,reply,"D"),branch) for reply in replies)
repeated=get_state_key(apply_move(after,replies[0],"D"),"A")
blocked=prove_capture(trap,[repeated],deadline=float("inf"),moves=[strike])
assert blocked.status=="NOT_PROVEN"
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]).parents[1]/"reference"))
from Tablut import Tablut

five=tuple(map(tuple,(".........","..D......","...A.....","..AKA....",
                     ".AAAXA...",".D...A...",".........",".........",".........")))
proof=prove_capture(five,deadline=float("inf"))
assert proof.status=="WIN" and len(proof.line)==5

def checked_child(position,move,side):
    game=Tablut()
    game.board=[list(row) for row in position]
    assert game.make_move(side=="A",move)
    child=apply_move(position,move,side)
    assert tuple(map(tuple,game.board))==child
    with redirect_stdout(StringIO()):
        ended=game.check_if_game_over(side=="D")
    expected=check_winner(child,"D" if side=="A" else "A")
    assert ended==(expected is not None)
    if ended:
        assert (game.winner or "DRAW")==expected
    return child

# Independently prove the selected five-ply move and rule-check all defending replies.
def forces_after(position, first, depth, path=()):
    child=checked_child(position,first,"A")
    path=(*path,get_state_key(position,"A"))
    result=check_winner(child,"D",path)
    if result is not None:
        return result=="A"
    if depth<3:
        return False
    path=(*path,get_state_key(child,"D"))
    for reply in get_legal_moves(child,"D"):
        state=checked_child(child,reply,"D")
        if check_winner(state,"A",path) is not None:
            return False
        if depth==3:
            wins=oracle(state,path)
            if not wins:
                return False
            assert check_winner(checked_child(state,next(iter(wins)),"A"),"D",path)=="A"
        elif not any(forces_after(state,move,depth-2,path) for move in get_legal_moves(state,"A")):
            return False
    return True

assert not any(forces_after(five,move,3) for move in get_legal_moves(five,"A"))
assert forces_after(five,proof.line[0],5)
from unittest.mock import patch
from src.enhanced_search import EnhancedSearch, SearchTimeout
start=initial_board()
base, alternative=get_legal_moves(start,"A")[:2]
alt_board=apply_move(start,alternative,"A")
def fake_visit(self, position, side, depth, alpha, beta, history, ply=0, moves=None):
    if ply==0:
        self.root_scores.update({base:0,alternative:0})
        return 0,(base,)
    assert depth==4 and alpha==float("-inf") and beta==float("inf")
    return (1 if position==alt_board else 0),()
def incomplete(self,*args,**kwargs):
    if args[0]==alt_board:
        raise SearchTimeout()
    return fake_visit(self,*args,**kwargs)
for visit,expected,status in ((fake_visit,alternative,"completed"),(incomplete,base,"incomplete")):
    with patch.object(EnhancedSearch,"visit",visit):
        stats={}
        selected=choose_enhanced(start,"A",deadline=perf_counter()+3,stats=stats,
            options=SearchOptions(deepen_ties=True),moves=[base,alternative,*get_legal_moves(start,"A")[2:13]])
        assert (selected,stats["tie_research"])==(expected,status)
def depth3_visit(self, position, side, depth, alpha, beta, history, ply=0, moves=None):
    if ply==0:
        if depth==4:
            raise SearchTimeout()
        self.root_scores.update({base:0,alternative:0})
        return 0,(base,)
    if depth>3:
        raise SearchTimeout()
    assert depth==3 and alpha==float("-inf") and beta==float("inf")
    return (1 if position==alt_board else 0),()
with patch.object(EnhancedSearch,"visit",depth3_visit):
    stats={}
    selected=choose_enhanced(start,"A",deadline=perf_counter()+3,stats=stats,
        options=SearchOptions(deepen_ties=True),moves=[base,alternative])
    assert selected==alternative and stats["full_width_depth"]==stats["completed_depth"]==3
    assert stats["candidate_depth"]==4 and stats["tie_changed_move"]
t=TranspositionTable(8)
t.store("key",4,1,EXACT,mate,context=frozenset({"history A"}))
assert t.probe("key",4,-10,10,context=frozenset({"history B"})) is None
assert t.probe("key",4,-10,10,context=frozenset({"history A"}))==1
"""
        subprocess.run([sys.executable, "-I", "-B", "-c", program, str(engine)], check=True)
