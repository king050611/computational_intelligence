"""V2: win-oriented constrained evolution with cheap screening and safe rematches."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from tempfile import mkdtemp
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config.evolution import BASE_WEIGHTS,EvolutionConfig
from config.experimental import SearchOptions
from scripts.benchmark import standings
from scripts.generate_openings import generate_openings
from src.evaluation import model_record
from src.evolution import initial_population,next_population,save_checkpoint,training_lock,fitness,rank_key,select_finalists,opponent_schedule


def publish(path,data):
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data,indent=2,allow_nan=False),encoding="utf-8")
    temporary.replace(path)


def source_hash():
    paths=[ROOT/p for p in ("scripts/train_evolution.py","scripts/benchmark.py","src/evolution.py","config/evolution.py","src/enhanced_search.py","src/features.py","src/experimental_player.py","src/time_control.py","src/tactics.py","src/evaluation.py","src/game.py","config/settings.py","config/experimental.py","reference/Tablut.py")]
    return hashlib.sha256(b"".join(p.read_bytes() for p in paths)).hexdigest()


def classify_rows(rows):
    """A control failure invalidates the experiment; never count a free win."""
    candidate_fault=control_fault=False
    for row in rows:
        for side in ("A","D"):
            issue=row["issues"][side]
            unsafe=any(issue[k] for k in ("illegal_moves","timeouts","exceptions","invalid_returns")) or row["attacker_seconds" if side=="A" else "defender_seconds"]>60
            if unsafe:
                if side==row["our_side"]:candidate_fault=True
                else:control_fault=True
    return "control_fault" if control_fault else "candidate_fault" if candidate_fault else "clean"


def prepare_stage(directory,attempt,name,options,pairs,generation,history):
    source=directory/("quick_openings.json" if name=="quick" else "selection_openings.json")
    entries=json.loads(source.read_text(encoding="utf-8"))["openings"]
    schedule=opponent_schedule(pairs,history is not None,generation)
    groups=[]
    for opponent in dict.fromkeys(schedule):
        subset=[entry for entry,label in zip(entries,schedule) if label==opponent]
        path=attempt/f"{name}_{opponent}_openings.json"
        path.write_text(json.dumps(dict(history_rule="restarted_opening",openings=subset)),encoding="utf-8")
        groups.append(dict(opponent=opponent,openings=path,game_count=2*len(subset)))
    historical=None
    if history is not None:
        historical=attempt/"historical_opponent.json"
        historical.write_text(json.dumps(model_record(history["weights"],generation=history["generation"])),encoding="utf-8")
    return dict(name=name,options=options,groups=groups,historical=historical,schedule=schedule)


def evaluate_candidate(directory,attempt,weights,index,generation,stage,config):
    model=attempt/f"{stage['name']}_i{index:03d}_model.json"
    model.write_text(json.dumps(model_record(weights,generation=generation,individual=index)),encoding="utf-8")
    all_rows=[];results=[]
    for group in stage["groups"]:
        accepted=None
        for retry in range(2):
            stem=f"{stage['name']}_i{index:03d}_{group['opponent']}_r{retry}"
            output=attempt/(stem+".json")
            opponent="evolutionary_dynamic" if group["opponent"]=="historical" else group["opponent"]
            opts=stage["options"]
            command=[sys.executable,str(ROOT/"scripts/benchmark.py"),"--strategy","evolutionary_dynamic","--model",str(model),"--opponent",opponent,"--openings",str(group["openings"]),"--seed",str(config.seed),"--max-depth",str(opts.max_depth),"--tt-capacity",str(opts.tt_capacity),"--output",str(output)]
            if group["opponent"]=="historical":command += ["--opponent-model",str(stage["historical"])]
            if not opts.order_moves:command.append("--no-ordering")
            with (attempt/(stem+".log")).open("w",encoding="utf-8") as log:
                completed=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
            try:
                data=json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
                fault=classify_rows(data["results"]) if data else "control_fault"
            except (OSError,ValueError,KeyError,TypeError):
                data=None;fault="control_fault"
            if fault=="candidate_fault":
                return dict(index=index,weights=weights,eligible=False,fitness=None,reason="candidate_fault",results=results+[output.relative_to(directory).as_posix()],stage=stage["name"])
            if fault=="clean" and completed.returncode==0 and data["games"]==group["game_count"] and len(data["results"])==group["game_count"]:
                accepted=data;results.append(output.relative_to(directory).as_posix());break
            # Retry control/environment failures once, keeping both attempts for audit.
        if accepted is None:
            raise RuntimeError(f"Control/environment failure repeated: {attempt/stem}")
        all_rows.extend(accepted["results"])
    table=standings(all_rows);row=table["overall"]
    trial=dict(index=index,weights=weights,eligible=True,fitness=fitness(row,config.win_reward),win_rate=row["wins"]/row["games"],loss_rate=row["losses"]/row["games"],points=row["points"],training_reward=config.win_reward*row["wins"]+row["draws"],standings=table,results=results,stage=stage["name"])
    (attempt/f"{stage['name']}_i{index:03d}_summary.json").write_text(json.dumps(trial,indent=2),encoding="utf-8")
    print(f"Generation {generation} {stage['name']} {index+1}: W{row['wins']} D{row['draws']} L{row['losses']}; fitness {trial['fitness']:.3f}; official {row['points']}/{2*row['games']}",flush=True)
    return trial


def run_generation(directory,population,generation,options,seed=42,*,config=None,incumbent=None):
    config=EvolutionConfig(seed=seed) if config is None else config
    attempt=Path(mkdtemp(prefix=f"g{generation:04d}_",dir=directory))
    quick=prepare_stage(directory,attempt,"quick",SearchOptions(config.quick_depth,options.tt_capacity,options.order_moves),config.quick_pairs,generation,incumbent)
    final=prepare_stage(directory,attempt,"final",options,config.final_pairs,generation,incumbent)
    quick_trials=[evaluate_candidate(directory,attempt,w,i,generation,quick,config) for i,w in enumerate(population)]
    finalists=select_finalists(quick_trials,config,incumbent["weights"] if incumbent else None)
    final_trials=[evaluate_candidate(directory,attempt,t["weights"],t["index"],generation,final,config) for t in finalists]
    ranked=sorted((t for t in final_trials if t["eligible"]),key=rank_key,reverse=True)
    if len(ranked)<config.elite or not any(tuple(t["weights"])==BASE_WEIGHTS for t in ranked):
        raise RuntimeError("Not enough safe finalists or missing safe manual control")
    if incumbent is not None and not any(tuple(t["weights"])==tuple(incumbent["weights"]) for t in ranked):
        raise RuntimeError("Incumbent could not be safely re-evaluated")
    screening=dict(quick_trials=quick_trials,final_trials=final_trials,finalist_indices=[t["index"] for t in finalists],quick_opponents=quick["schedule"],final_opponents=final["schedule"],attempt=attempt.relative_to(directory).as_posix())
    (attempt/"screening.json").write_text(json.dumps(screening,indent=2),encoding="utf-8")
    return ranked,screening


def export_best(directory,checkpoint):
    best=checkpoint["best"]
    if best is not None:
        publish(directory/"best.json",model_record(best["weights"],generation=best["generation"],fitness=best["fitness"],win_reward=checkpoint["config"]["win_reward"],official_points=best["points"],selection_only=True,source_commit=checkpoint["source_commit"],source_hash=checkpoint["source_hash"]))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--generations",type=int,default=1,help="Additional complete V2 generations")
    parser.add_argument("--resume",action="store_true")
    floats=("crossover","mutation","sigma","bound")
    for name in EvolutionConfig.__dataclass_fields__:
        if name in ("constrained","final_pairs"):continue
        parser.add_argument("--"+name.replace("_","-"),type=float if name in floats else int)
    parser.add_argument("--pairs","--final-pairs",dest="final_pairs",type=int)
    signs=parser.add_mutually_exclusive_group()
    signs.add_argument("--constrained",dest="constrained",action="store_true",default=None)
    signs.add_argument("--unconstrained",dest="constrained",action="store_false")
    parser.add_argument("--max-depth",type=int)
    parser.add_argument("--tt-capacity",type=int)
    parser.add_argument("--no-ordering",action="store_true",default=None)
    args=parser.parse_args(argv)
    if args.generations<1:parser.error("Generations must be positive")
    directory=args.output_dir.resolve();directory.mkdir(parents=True,exist_ok=True)
    try:
        with training_lock(directory):
            paths=sorted(directory.glob("checkpoint-*.json"))
            explicit={name:getattr(args,name) for name in EvolutionConfig.__dataclass_fields__ if getattr(args,name) is not None}
            if args.resume:
                if not paths:raise ValueError("No V2 checkpoint to resume")
                checkpoint=json.loads(paths[-1].read_text(encoding="utf-8"))
                if checkpoint.get("schema_version")!=2:raise ValueError("Legacy training cannot resume into V2; start a new directory")
                config=EvolutionConfig(**checkpoint["config"])
                if any(getattr(config,k)!=v for k,v in explicit.items()):raise ValueError("Resume cannot change genetic/screening configuration")
                options=SearchOptions(**checkpoint["search_options"])
                if any(value is not None and value!=getattr(options,name) for name,value in (("max_depth",args.max_depth),("tt_capacity",args.tt_capacity))):raise ValueError("Resume cannot change search configuration")
                if args.no_ordering and options.order_moves:raise ValueError("Resume cannot change ordering")
                if source_hash()!=checkpoint["source_hash"]:raise ValueError("Training/search source changed; start a new run")
                for filename,digest in checkpoint["opening_hashes"].items():
                    if hashlib.sha256((directory/filename).read_bytes()).hexdigest()!=digest:raise ValueError("Training openings changed")
            else:
                if paths or (directory/"selection_openings.json").exists():raise ValueError("Run exists; use --resume or a new directory")
                config=EvolutionConfig(**explicit)
                options=SearchOptions(4 if args.max_depth is None else args.max_depth,20000 if args.tt_capacity is None else args.tt_capacity,not args.no_ordering)
                if config.quick_depth>options.max_depth:raise ValueError("Quick depth cannot exceed final depth")
                hashes={};seen=set()
                for filename,count,seed in (("quick_openings.json",config.quick_pairs,config.seed),("selection_openings.json",config.final_pairs,config.seed+1)):
                    data=generate_openings(count,seed)
                    boards={tuple(map(tuple,e["board"])) for e in data["openings"]}
                    if boards&seen:raise ValueError("Quick/final openings overlap; choose a different seed")
                    seen|=boards
                    path=directory/filename;path.write_text(json.dumps(data),encoding="utf-8");hashes[filename]=hashlib.sha256(path.read_bytes()).hexdigest()
                checkpoint=dict(schema_version=2,generation=0,config=asdict(config),search_options=asdict(options),opening_hashes=hashes,population=initial_population(config),best=None,source_hash=source_hash(),source_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,encoding="utf-8").strip(),source_changes=subprocess.check_output(["git","status","--porcelain","--","."],cwd=ROOT,encoding="utf-8"))
                save_checkpoint(directory,checkpoint)
            export_best(directory,checkpoint)
            for _ in range(args.generations):
                if (directory/"STOP").exists():print("STOP requested",flush=True);break
                generation=checkpoint["generation"]+1
                ranked,screening=run_generation(directory,checkpoint["population"],generation,options,config.seed,config=config,incumbent=checkpoint["best"])
                # A changed opponent pool makes past scores incomparable. The incumbent
                # is re-tested; this generation's best is selected from current final matches.
                best=dict(ranked[0],generation=generation)
                checkpoint=dict(checkpoint,generation=generation,trials=ranked,screening=screening,best=best,population=next_population([t["weights"] for t in ranked],config,generation))
                save_checkpoint(directory,checkpoint);export_best(directory,checkpoint)
                print(f"Checkpoint {generation}: current-pool best fitness {best['fitness']:.3f}; official points {best['points']}",flush=True)
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:
        parser.exit(1,f"Evolution stopped: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130,"Interrupted; resume from the last completed generation.\n")

if __name__=="__main__":main()
