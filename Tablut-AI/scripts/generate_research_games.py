"""Generate resumable, paired research replays through the course referee."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import contextlib
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def worker(spec):
    sys.path.insert(0,spec["engine"])
    from config.experimental import SearchOptions
    from src.evaluation import load_evaluator
    from src.experimental_player import ExperimentalPlayer
    from src import time_control
    import src.experimental_player as adapter
    for module in (time_control,adapter):
        if hasattr(module,"GAME_TIME_LIMIT"):
            module.GAME_TIME_LIMIT=spec["seconds"]
    settings={"max_depth":spec["depth"]}
    if spec["nodes"]:
        settings["node_budget"]=spec["nodes"]
    model=load_evaluator(spec["model"]) if spec["model"] else None
    if spec.get("attacker_strategy"):
        from src.evaluation import AttackerStrategyEvaluator, RoleEvaluator
        if model is None:
            raise ValueError("An attacker strategy needs a base model")
        attack = model.attacker if isinstance(model, RoleEvaluator) else model
        defense = model.defender if isinstance(model, RoleEvaluator) else model
        model = RoleEvaluator(AttackerStrategyEvaluator(attack, spec["attacker_strategy"]), defense)
    bot=ExperimentalPlayer("evolutionary_dynamic" if model else "enhanced_dynamic",
                           opening=spec["board"],evaluator=model,options=SearchOptions(**settings),record_search=True)
    print("ready",flush=True)
    for line in sys.stdin:
        side,board=json.loads(line)
        move=(bot.play_attacker if side=="A" else bot.play_defender)(board)
        print(json.dumps([move,bot.last_search_stats]),flush=True)


class Engine:
    def __init__(self,spec,board):
        self.process=subprocess.Popen([sys.executable,"-I",__file__,"--worker",json.dumps(dict(spec,board=board))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding="utf-8",bufsize=1)
        self.reader=ThreadPoolExecutor(max_workers=1)
        self.seconds=spec["seconds"]
        try:
            if self.read_line(10).strip()!="ready":
                raise RuntimeError(f"Engine startup failed for {spec['engine']}")
        except BaseException:
            self.close()
            raise
        self.last_search_stats=None

    def read_line(self,seconds):
        try:
            return self.reader.submit(self.process.stdout.readline).result(timeout=seconds)
        except TimeoutError:
            self.process.kill()
            raise TimeoutError("Research engine exceeded response deadline") from None

    def play(self,side,board):
        self.process.stdin.write(json.dumps([side,board])+"\n")
        self.process.stdin.flush()
        move,self.last_search_stats=json.loads(self.read_line(self.seconds))
        return move

    def play_attacker(self,board):
        return self.play("A",board)

    def play_defender(self,board):
        return self.play("D",board)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.reader.shutdown(wait=True)
        self.process.stdout.close()


class MatchFault(RuntimeError):
    def __init__(self, message, faulty_sides):
        super().__init__(message)
        self.faulty_sides=frozenset(faulty_sides)


def play_job(job):
    from scripts.replay_demo import Recorder, ObservedPlayer, snapshot
    from scripts.analyze_history import normalize_replay
    import Tablut
    file,entry,side,specs,seconds,seed=job
    Tablut.TIME_BUDGET=seconds
    game=Recorder()
    game.board=snapshot(entry["board"])
    game.initial_board=snapshot(game.board)
    engines=[]
    try:
        for spec in specs:
            engines.append(Engine(spec,game.board))
        players=[ObservedPlayer(bot,game,label) for bot,label in zip(engines,("candidate","control"))]
        a,d=players if side=="A" else players[::-1]
        with contextlib.redirect_stdout(io.StringIO()) as log:
            game.play(a,d)
        elapsed=[sum(p.timed.times) for p in (a,d)]
        limits=[spec["seconds"] for spec in specs]
        if side=="D":
            limits.reverse()
        message=log.getvalue()
        faults=set()
        for tag,label,player,time,limit in zip(("A","D"),("Attackers","Defenders"),(a,d),elapsed,limits):
            if (player.timed.errors or player.timed.invalid_returns or time>limit
                    or f"Illegal move by {label}" in message or f"{label} exceeded time limit" in message
                    or f"Exception caught for {label}" in message):
                faults.add(tag)
        if not game.termination or faults:
            detail=dict(side=side,faulty_sides=sorted(faults),log=message,elapsed=elapsed,
                        initial_board=game.initial_board,moves=game.events,pending=game.pending)
            quarantine=file.parent/"rejected"
            quarantine.mkdir(exist_ok=True)
            (quarantine/file.name).write_text(json.dumps(detail),encoding="utf-8")
            raise MatchFault(f"{file.name}: referee fault: {message}",faults)
        row=dict(game=int(file.stem),opening_id=entry["id"],seed=seed,our_side=side,
                 strategies=dict(A=a.strategy,D=d.strategy),initial_board=game.initial_board,
                 final_board=snapshot(game.board),moves=game.events,result=game.termination,
                 accepted_moves=len(game.events),attacker_seconds=elapsed[0],defender_seconds=elapsed[1],
                 referee_log=log.getvalue())
        valid,error=normalize_replay(row)
        if not valid:
            raise RuntimeError(f"{file.name}: replay validation failed: {error}")
        spent=Counter()
        for event in row["moves"]:
            turn=event["player"]
            limit=limits[0 if turn=="A" else 1]
            event["remaining_game_seconds_before"]=max(0,limit-spent[turn])
            spent[turn]+=event["elapsed_seconds"]
        temp=file.with_suffix(".tmp")
        temp.write_text(json.dumps(row),encoding="utf-8")
        temp.replace(file)
        return row
    finally:
        for bot in engines:
            bot.close()


def fingerprint(directory):
    return {p.relative_to(directory).as_posix():sha256(p.read_bytes()).hexdigest()
            for folder in ("src","config") for p in sorted((directory/folder).rglob("*.py"))}


def select_openings(count, seed):
    from scripts.generate_openings import generate_openings
    from scripts.build_strategy_dataset import symmetry

    excluded=set()
    for path in (ROOT/"data/positions").rglob("*holdout*_positions.jsonl"):
        for line in path.read_bytes().splitlines():
            if line.strip():
                item=json.loads(line)
                excluded.add(symmetry(item["board"],item["side"]))
    openings=[]
    for entry in generate_openings(count*2,seed)["openings"]:
        key=symmetry(entry["board"],"A")
        if key not in excluded:
            excluded.add(key)
            openings.append(dict(entry,id=len(openings)+1))
            if len(openings)==count:
                break
    if len(openings)!=count:
        raise ValueError("Not enough disjoint openings")
    return openings


def main():
    from scripts.replay_demo import write_replay
    from scripts.analyze_history import normalize_replay
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--pairs",type=int,default=10)
    parser.add_argument("--seed",type=int,default=88921)
    parser.add_argument("--seconds",type=int,default=60)
    parser.add_argument("--candidate-seconds",type=int)
    parser.add_argument("--control-seconds",type=int)
    parser.add_argument("--workers",type=int,default=1)
    parser.add_argument("--candidate-side",choices=("A","D"))
    parser.add_argument("--resume",action="store_true")
    for prefix in ("candidate","control"):
        parser.add_argument(f"--{prefix}-engine",type=Path,default=ROOT)
        parser.add_argument(f"--{prefix}-model",type=Path)
        parser.add_argument(f"--{prefix}-depth",type=int,default=4)
        parser.add_argument(f"--{prefix}-nodes",type=int,default=0)
    parser.add_argument("--attacker-strategy", choices=("A1", "A2", "A3"))
    args=parser.parse_args()
    if args.attacker_strategy and (args.candidate_side != "A" or not args.candidate_model):
        parser.error("--attacker-strategy requires a fixed attacker and a candidate model")
    if min(args.pairs,args.workers)<1 or args.seconds<=5:
        parser.error("Positive pairs/workers and a budget above five seconds required")
    if args.workers>1 and (not(args.candidate_nodes and args.control_nodes)
                          or args.workers>min(4,max(1,(os.cpu_count() or 1)//2))):
        parser.error("Parallelism requires fixed nodes for both engines and is capped by CPU count")
    specs=[]
    for label in ("candidate","control"):
        engine=getattr(args,label+"_engine").resolve()
        model=getattr(args,label+"_model")
        depth,nodes=getattr(args,label+"_depth"),getattr(args,label+"_nodes")
        files=fingerprint(engine)
        if not files or depth<1 or nodes<0:
            parser.error(f"Invalid {label} engine or search configuration")
        cap=getattr(args,label+"_seconds")
        # A fixed-node research opponent can receive extra time while the clock-controlled side keeps 60s.
        if cap is None:
            cap=min(60,args.seconds) if not nodes and (args.candidate_nodes or args.control_nodes) else args.seconds
        if not 5<cap<=args.seconds:
            parser.error("Per-engine budget must be above five seconds and within the referee cap")
        specs.append(dict(engine=str(engine),model=str(model.resolve()) if model else None,
                          model_sha256=sha256(model.read_bytes()).hexdigest() if model else None,
                          files=files,depth=depth,nodes=nodes,seconds=cap))
    if args.attacker_strategy:
        specs[0]["attacker_strategy"] = args.attacker_strategy
    openings=select_openings(args.pairs,args.seed)
    mode="standard_games" if args.seconds==60 and not any(s["nodes"] for s in specs) else "high_budget_games"
    # Serialize the configuration before comparison to normalize tuple/list representation.
    manifest=json.loads(json.dumps(dict(seed=args.seed,specs=specs,openings=openings,mode=mode,
        referee_sha256=sha256((ROOT/"reference/Tablut.py").read_bytes()).hexdigest(),
        candidate_side=args.candidate_side,workers=args.workers)))
    path=args.output/"manifest.json"
    if args.resume:
        if json.loads(path.read_bytes())!=manifest:
            raise ValueError("Run configuration, openings or frozen sources changed")
    else:
        args.output.mkdir(parents=True,exist_ok=False)
        path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    openings=manifest["openings"]
    from src.evolution import training_lock
    with training_lock(args.output):
        run_games(args,manifest,openings,specs,normalize_replay,write_replay)


def run_games(args,manifest,openings,specs,normalize_replay,write_replay):
    folder=args.output/"individual"
    folder.mkdir(exist_ok=True)
    jobs=[]
    rows=[]
    for entry in openings:
        for side in (args.candidate_side,) if args.candidate_side else ("A","D"):
            file=folder/f"{len(rows)+len(jobs)+1:04d}.json"
            if file.exists():
                row=json.loads(file.read_bytes())
                if not normalize_replay(row)[0] or row["our_side"]!=side or row["initial_board"]!=entry["board"]:
                    raise ValueError(f"Invalid saved replay: {file}")
                rows.append(row)
            else:
                jobs.append((file,entry,side,specs,args.seconds,args.seed))
    if args.workers==1:
        for job in jobs:
            row=play_job(job)
            rows.append(row)
            print(args.output.name,row["game"],row["result"],flush=True)
    else:
        with ProcessPoolExecutor(args.workers) as pool:
            rows.extend(pool.map(play_job,jobs))
    write_replay(dict(schema_version="1.1",games=sorted(rows,key=lambda r:r["game"]),**manifest),args.output)


if __name__=="__main__":
    if len(sys.argv)==3 and sys.argv[1]=="--worker":
        worker(json.loads(sys.argv[2]))
    else:
        main()
