"""Compare first attack divergences from the archived V5/E1 paired games."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from scripts.generate_research_games import ROOT, fingerprint

PROBE = """
import json,sys
from time import perf_counter
sys.path.insert(0,sys.argv[1])
from config.experimental import SearchOptions
from src.evaluation import load_evaluator
from src.enhanced_search import choose_enhanced
from src.game import apply_move,check_winner,get_legal_moves,get_state_key,get_piece_moves

evaluator=load_evaluator(sys.argv[2])
for row in json.load(sys.stdin):
    board=tuple(map(tuple,row["board"]))
    history=tuple(get_state_key(tuple(map(tuple,b)),s) for b,s in row["history"])
    opts=SearchOptions(max_depth=row["depth"],node_budget=row["budget"])
    stats={}
    start=perf_counter()
    candidates=[tuple(map(tuple,m)) for m in (row["recorded_base"],row["recorded_e1"])] if row["focused"] else None
    move=choose_enhanced(board,"A",deadline=start+35,history=history,evaluator=evaluator,stats=stats,options=opts,moves=candidates)
    result=dict(move=move,depth=stats["completed_depth"],score=stats["score"],nodes=stats["nodes"],seconds=perf_counter()-start)
    if move:
        after=apply_move(board,move,"A")
        path=history+(get_state_key(board,"A"),)
        result["rule_result"]=check_winner(after,"D",path)
        king=next(((r,c) for r in range(9) for c in range(9) if after[r][c]=="K"),None)
        result["defender_direct_escapes"]=sum(any(x in (0,8) for x in end) for _,end in get_piece_moves(after,king,"D")) if king else 0
        result["potential_captures_before_defender_reply"]=sum(
            check_winner(apply_move(after,m,"A"),"D")=="A" for m in get_legal_moves(after,"A")
        ) if king and result["rule_result"] is None else 0
    print(json.dumps(result),flush=True)
"""


def load(path):
    return json.loads(path.read_bytes())


def cases_for(base, trial):
    for number in (5,8,9,10,12,14):
        a,b = base[number],trial[number]
        if a["initial_board"] != b["initial_board"]:
            raise ValueError(f"Openings differ: {number}")
        history = []
        for left,right in zip(a["moves"],b["moves"]):
            if left["move"] != right["move"]:
                if left["player"] != "A" or left["board_before"] != right["board_before"]:
                    raise ValueError(f"First divergence is not a shared attacker turn: {number}")
                yield dict(opening_id=number,ply=left["ply"],board=left["board_before"],history=history,
                           recorded_base=left["move"],recorded_e1=right["move"],results={})
                break
            history.append((left["board_before"],left["player"]))


def main():
    baseline = ROOT/"reports/v7_attacker_base_20"
    trial = ROOT/"reports/v7_attacker_e1_20"
    predecessor = ROOT/"reports/v7_baseline_engine"
    model = ROOT/"models/attacker/best.json"
    specs = [load(p/"manifest.json")["specs"][0] for p in (baseline,trial)]
    if fingerprint(predecessor) != specs[0]["files"] or any(
        sha256(model.read_bytes()).hexdigest()!=spec["model_sha256"] for spec in specs
    ):
        raise ValueError("Historical baseline or model hash mismatch")
    games = [{g["opening_id"]:g for g in load(p/"games.json")["games"]} for p in (baseline,trial)]
    cases = list(cases_for(*games))
    with TemporaryDirectory(dir=ROOT) as tmp:
        restored = Path(tmp)
        for rel,digest in specs[1]["files"].items():
            blob = subprocess.check_output(["git","show",f"364419a:Tablut-AI/engines/attacker/{rel}"],cwd=ROOT)
            if rel == "config/experimental.py":
                blob = blob.replace(b"attacker_ordering: bool = False",b"attacker_ordering: bool = True")
            if sha256(blob).hexdigest()!=digest:
                blob = blob.replace(b"\r\n",b"\n").replace(b"\n",b"\r\n")
            if sha256(blob).hexdigest()!=digest:
                raise ValueError(f"Cannot verify restored E1 file: {rel}")
            path=restored/rel
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(blob)
        current=ROOT/"engines/attacker"
        for name,engine,depth,budget in (
            ("V5",predecessor,4,15000),("E1",restored,4,15000),("R0",current,4,15000),
            ("reference5",current,5,100000),("reference6",current,6,220000),
            ("focused5",current,5,180000),("focused6",current,6,360000),
        ):
            result=subprocess.run([sys.executable,"-I","-B","-c",PROBE,str(engine),str(model)],
                                  input=json.dumps([dict(c,depth=depth,budget=budget,focused=name.startswith("focused")) for c in cases]),
                                  text=True,capture_output=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
            outputs=result.stdout.splitlines()
            if len(outputs)!=len(cases):
                raise RuntimeError(f"Incomplete diagnostic: {name}")
            for case,line in zip(cases,outputs):
                case["results"][name]=json.loads(line)
            print(name,[(c["opening_id"],c["results"][name]["depth"]) for c in cases],flush=True)
    path=ROOT/"reports/experiments/guide4/positions.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(dict(cases=cases,note="Target depth can exceed completed depth. Focused runs compare the two recorded moves only."),indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
