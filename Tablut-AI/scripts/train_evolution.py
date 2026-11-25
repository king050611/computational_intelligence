"""Finite, resumable genetic training through the official match runner."""
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
from config.evolution import EvolutionConfig
from config.experimental import SearchOptions
from scripts.generate_openings import generate_openings
from src.evaluation import model_record
from src.evolution import initial_population,next_population,save_checkpoint,training_lock


def publish(path,data):
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data,indent=2,allow_nan=False),encoding="utf-8")
    temporary.replace(path)


def run_generation(directory,population,generation,options,seed=42):
    trials=[]
    attempt=Path(mkdtemp(prefix=f"g{generation:04d}_",dir=directory))
    for index,weights in enumerate(population):
        stem=f"g{generation:04d}_i{index:03d}"
        model=attempt/(stem+"_model.json")
        result=attempt/(stem+"_match.json")
        record=model_record(weights,generation=generation,individual=index)
        model.write_text(json.dumps(record,indent=2),encoding="utf-8")
        command=[sys.executable,str(ROOT/"scripts/benchmark.py"),"--strategy","evolutionary_dynamic",
                 "--model",str(model),"--seed",str(seed),"--opponent","enhanced_dynamic","--openings",str(directory/"selection_openings.json"),
                 "--max-depth",str(options.max_depth),"--tt-capacity",str(options.tt_capacity),"--output",str(result)]
        if not options.order_moves:
            command.append("--no-ordering")
        with (attempt/(stem+".log")).open("w",encoding="utf-8") as log:
            completed=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        if completed.returncode:
            raise RuntimeError(f"Fitness failed: {attempt/(stem+'.log')}")
        data=json.loads(result.read_text(encoding="utf-8"))
        if any(row["illegal_moves"] or row["timeouts"] or row["exceptions"] or row["invalid_returns"] for row in data["results"]):
            raise RuntimeError("Invalid fitness match; candidate must not be promoted")
        trial=dict(weights=weights,points=data["standings"]["overall"]["points"],standings=data["standings"],result=result.relative_to(directory).as_posix())
        trials.append(trial)
        print(f"Generation {generation}, individual {index+1}/{len(population)}: {trial['points']}/{2*data['games']} points",flush=True)
    return sorted(trials,key=lambda trial:trial["points"],reverse=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--generations",type=int,default=10,help="Additional generations")
    parser.add_argument("--resume",action="store_true")
    for name,kind in (("population",int),("elite",int),("crossover",float),("mutation",float),("sigma",float),("bound",float),("seed",int),("pairs",int),("max-depth",int),("tt-capacity",int)):
        parser.add_argument("--"+name,type=kind)
    parser.add_argument("--no-ordering",action="store_true",default=None)
    args=parser.parse_args(argv)
    if args.generations<1:
        parser.error("Generations must be positive")
    directory=args.output_dir.resolve()
    directory.mkdir(parents=True,exist_ok=True)
    try:
        with training_lock(directory):
            paths=sorted(directory.glob("checkpoint-*.json"))
            explicit={name:getattr(args,name) for name in EvolutionConfig.__dataclass_fields__ if getattr(args,name) is not None}
            if args.resume:
                if not paths:
                    raise ValueError("No evolution checkpoint to resume")
                checkpoint=json.loads(paths[-1].read_text(encoding="utf-8"))
                config=EvolutionConfig(**checkpoint["config"])
                if any(getattr(config,key)!=value for key,value in explicit.items()):
                    raise ValueError("Resume cannot change genetic configuration")
                options=SearchOptions(**checkpoint["search_options"])
                for name,value in (("max_depth",args.max_depth),("tt_capacity",args.tt_capacity),("pairs",args.pairs)):
                    saved=checkpoint["pairs"] if name=="pairs" else getattr(options,name)
                    if value is not None and value!=saved:
                        raise ValueError("Resume cannot change the evaluation suite")
                if args.no_ordering is not None and options.order_moves:
                    raise ValueError("Resume cannot change move ordering")
                if hashlib.sha256((directory/"selection_openings.json").read_bytes()).hexdigest()!=checkpoint["openings_sha256"]:
                    raise ValueError("Selection openings were changed")
            else:
                if paths or (directory/"selection_openings.json").exists():
                    raise ValueError("Run exists; use --resume or a new directory")
                config=EvolutionConfig(**explicit)
                pairs=4 if args.pairs is None else args.pairs
                if pairs<1:
                    raise ValueError("Opening pairs must be positive")
                options=SearchOptions(4 if args.max_depth is None else args.max_depth,20000 if args.tt_capacity is None else args.tt_capacity,not args.no_ordering)
                opening=directory/"selection_openings.json"
                opening.write_text(json.dumps(generate_openings(pairs,config.seed)),encoding="utf-8")
                sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
                checkpoint=dict(generation=0,config=asdict(config),search_options=asdict(options),pairs=pairs,
                                openings_sha256=hashlib.sha256(opening.read_bytes()).hexdigest(),
                                population=initial_population(config),best=None,source_commit=sha,
                                source_changes=subprocess.check_output(["git","status","--porcelain","--","."],cwd=ROOT,text=True))
                save_checkpoint(directory,checkpoint)
            if checkpoint["best"] is not None:
                best=checkpoint["best"]
                publish(directory/"best.json",model_record(best["weights"],generation=best["generation"],selection_points=best["points"],selection_only=True,openings_sha256=checkpoint["openings_sha256"],source_commit=checkpoint["source_commit"]))
            for _ in range(args.generations):
                if (directory/"STOP").exists():
                    print("STOP requested; no new generation started",flush=True)
                    break
                generation=checkpoint["generation"]+1
                # A crash may leave this generation's unpublished individual files. Replay them
                # from scratch; only a fully checkpointed generation is trusted.
                ranked=run_generation(directory,checkpoint["population"],generation,options,config.seed)
                best=checkpoint["best"]
                if best is None or ranked[0]["points"]>best["points"]:
                    best=dict(ranked[0],generation=generation)
                checkpoint=dict(checkpoint,generation=generation,trials=ranked,best=best,
                                population=next_population([r["weights"] for r in ranked],config,generation))
                save_checkpoint(directory,checkpoint)
                publish(directory/"best.json",model_record(best["weights"],generation=best["generation"],selection_points=best["points"],selection_only=True,openings_sha256=checkpoint["openings_sha256"],source_commit=checkpoint["source_commit"]))
                print(f"Checkpoint {generation}: best generation {best['generation']}, {best['points']} selection points",flush=True)
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:
        parser.exit(1,f"Evolution stopped: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130,"Interrupted; resume from the last completed generation.\n")

if __name__=="__main__":
    main()
