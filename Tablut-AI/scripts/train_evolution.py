"""V3: win-oriented constrained evolution with weight-unique populations.

Changes over V2 (training mechanism only, never the referee, search or features):

* populations are weight-unique (``src.evolution.initial_population``/``next_population``);
* finalist slots are weight-unique and reserve one diversity slot;
* a previous champion can seed a fresh run through ``--initial-model`` or
  ``--initial-checkpoint`` instead of bypassing the source-hash resume guard;
* each candidate reports attacker/defender rates, official points, timing and depth.
"""
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
from config.evolution import BASE_WEIGHTS,GENE_SIGNS,EvolutionConfig
from config.experimental import SearchOptions
from scripts.benchmark import standings
from scripts.generate_openings import generate_openings
from src.evaluation import WeightedEvaluator,load_evaluator,migrate_weights,model_record
from src.evolution import (fitness,initial_population,next_population,opponent_schedule,
                           population_report,rank_key,select_finalists,save_checkpoint,training_lock)


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


def _own_search_stats(row):
    stats=(row.get("search_stats") or {}).get(row.get("our_side","A")) or []
    return [entry for entry in stats if isinstance(entry,dict)]


def trial_statistics(rows,win_reward,attacker_weight=1.0,defender_weight=1.0):
    """Attacker/defender rates, official points, timing and depth for one candidate."""
    table=standings(rows)
    def block(entry):
        games=entry["games"]
        denominator=games if games else 1
        return dict(games=games,wins=entry["wins"],draws=entry["draws"],losses=entry["losses"],
                    win_rate=entry["wins"]/denominator,draw_rate=entry["draws"]/denominator,
                    loss_rate=entry["losses"]/denominator,points=entry["points"],
                    official_rate=entry["points"]/(2*denominator))
    overall=block(table["overall"])
    overall["training_fitness"]=fitness(table,win_reward,attacker_weight,defender_weight)
    moves=[float(row.get("our_mean_move_seconds") or 0.0) for row in rows]
    totals=[float(row.get("attacker_seconds" if row.get("our_side")=="A" else "defender_seconds") or 0.0)
            for row in rows]
    depths=[entry.get("completed_depth") for row in rows for entry in _own_search_stats(row)
            if isinstance(entry.get("completed_depth"),int)]
    return dict(overall=overall,attacker=block(table["attacker"]),defender=block(table["defender"]),
                mean_move_seconds=(sum(moves)/len(moves)) if moves else 0.0,
                mean_total_seconds=(sum(totals)/len(totals)) if totals else 0.0,
                max_total_seconds=max(totals) if totals else 0.0,
                mean_completed_depth=(sum(depths)/len(depths)) if depths else None,
                recorded_depths=len(depths))


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


def evaluate_candidate(directory,attempt,weights,index,generation,stage,config,record_search=False):
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
            if record_search:command.append("--record-search")
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
    trial=dict(index=index,weights=weights,eligible=True,fitness=fitness(table,config.win_reward,config.attacker_game_weight,config.defender_game_weight),
               win_rate=row["wins"]/row["games"],loss_rate=row["losses"]/row["games"],points=row["points"],
               training_reward=config.win_reward*row["wins"]+row["draws"],standings=table,
               statistics=trial_statistics(all_rows,config.win_reward,config.attacker_game_weight,config.defender_game_weight),
               results=results,stage=stage["name"])
    (attempt/f"{stage['name']}_i{index:03d}_summary.json").write_text(json.dumps(trial,indent=2),encoding="utf-8")
    print(f"Generation {generation} {stage['name']} {index+1}: W{row['wins']} D{row['draws']} L{row['losses']}; fitness {trial['fitness']:.3f}; official {row['points']}/{2*row['games']}",flush=True)
    return trial


def run_generation(directory,population,generation,options,seed=42,*,config=None,incumbent=None,record_search=False):
    config=EvolutionConfig(seed=seed) if config is None else config
    attempt=Path(mkdtemp(prefix=f"g{generation:04d}_",dir=directory))
    quick=prepare_stage(directory,attempt,"quick",SearchOptions(config.quick_depth,options.tt_capacity,options.order_moves),config.quick_pairs,generation,incumbent)
    final=prepare_stage(directory,attempt,"final",options,config.final_pairs,generation,incumbent)
    quick_trials=[evaluate_candidate(directory,attempt,w,i,generation,quick,config,record_search) for i,w in enumerate(population)]
    finalists=select_finalists(quick_trials,config,incumbent["weights"] if incumbent else None)
    final_trials=[evaluate_candidate(directory,attempt,t["weights"],t["index"],generation,final,config,record_search) for t in finalists]
    ranked=sorted((t for t in final_trials if t["eligible"]),key=rank_key,reverse=True)
    if len(ranked)<config.elite or not any(tuple(t["weights"])==BASE_WEIGHTS for t in ranked):
        raise RuntimeError("Not enough safe finalists or missing safe manual control")
    if incumbent is not None and not any(tuple(t["weights"])==tuple(incumbent["weights"]) for t in ranked):
        raise RuntimeError("Incumbent could not be safely re-evaluated")
    selection=[dict(index=t["index"],weights=list(t["weights"]),selection_reason=t.get("selection_reason"),
                    quick_rank=t.get("quick_rank"),distance_from_champion=t.get("distance_from_champion"),
                    quick_fitness=t["fitness"]) for t in finalists]
    screening=dict(quick_trials=quick_trials,final_trials=final_trials,finalist_indices=[t["index"] for t in finalists],
                   finalist_selection=selection,quick_opponents=quick["schedule"],final_opponents=final["schedule"],
                   attempt=attempt.relative_to(directory).as_posix())
    (attempt/"screening.json").write_text(json.dumps(screening,indent=2),encoding="utf-8")
    return ranked,screening


def export_best(directory,checkpoint):
    best=checkpoint["best"]
    if best is not None and best.get("fitness") is not None:
        publish(directory/"best.json",model_record(best["weights"],generation=best["generation"],fitness=best["fitness"],win_reward=checkpoint["config"]["win_reward"],official_points=best["points"],selection_only=True,source_commit=checkpoint["source_commit"],source_hash=checkpoint["source_hash"]))


def load_initial_weights(args,config):
    """Read warm-start weights from a model or an earlier checkpoint, with provenance."""
    path=args.initial_model if args.initial_model is not None else args.initial_checkpoint
    if path is None:
        return None,None
    path=Path(path)
    if not path.is_file():
        raise ValueError(f"Initial weights file not found: {path}")
    raw=path.read_bytes()
    provenance=dict(kind="model" if args.initial_model is not None else "checkpoint",
                    path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    if args.initial_model is not None:
        weights=tuple(float(w) for w in load_evaluator(path).weights)
    else:
        data=json.loads(raw.decode("utf-8"))
        if data.get("schema_version")!=2:
            raise ValueError("Initial checkpoint must use schema 2")
        best=data.get("best") or {}
        if not best.get("weights"):
            raise ValueError("Initial checkpoint carries no champion weights")
        weights=tuple(float(w) for w in WeightedEvaluator(migrate_weights(tuple(best["weights"]))).weights)
        provenance.update(generation=best.get("generation"),fitness=best.get("fitness"),points=best.get("points"))
    if config.constrained and any(w*sign<0 for w,sign in zip(weights,GENE_SIGNS)):
        raise ValueError("Initial weights violate the constrained sign prior")
    provenance["weights"]=list(weights)
    return weights,provenance


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--generations",type=int,default=1,help="Additional complete V3 generations")
    parser.add_argument("--resume",action="store_true")
    start=parser.add_mutually_exclusive_group()
    start.add_argument("--initial-model",type=Path,help="Six-feature model JSON seeding a new V3 population")
    start.add_argument("--initial-checkpoint",type=Path,help="Earlier checkpoint-*.json seeding a new V3 population")
    parser.add_argument("--record-search",action="store_true",help="Record per-decision search statistics for every training game")
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
                if not paths:raise ValueError("No V3 checkpoint to resume")
                if args.initial_model or args.initial_checkpoint:raise ValueError("Resume cannot reseed the population")
                checkpoint=json.loads(paths[-1].read_text(encoding="utf-8"))
                if checkpoint.get("schema_version")!=2:raise ValueError("Legacy training cannot resume into V3; start a new directory")
                config=EvolutionConfig(**checkpoint["config"])
                if any(getattr(config,k)!=v for k,v in explicit.items()):raise ValueError("Resume cannot change genetic/screening configuration")
                options=SearchOptions(**checkpoint["search_options"])
                if any(value is not None and value!=getattr(options,name) for name,value in (("max_depth",args.max_depth),("tt_capacity",args.tt_capacity))):raise ValueError("Resume cannot change search configuration")
                if args.no_ordering and options.order_moves:raise ValueError("Resume cannot change ordering")
                if source_hash()!=checkpoint["source_hash"]:raise ValueError("Training/search source changed; start a new run")
                for filename,digest in checkpoint["opening_hashes"].items():
                    if hashlib.sha256((directory/filename).read_bytes()).hexdigest()!=digest:raise ValueError("Training openings changed")
                record_search=bool(checkpoint.get("record_search")) or args.record_search
            else:
                if paths or (directory/"selection_openings.json").exists():raise ValueError("Run exists; use --resume or a new directory")
                config=EvolutionConfig(**explicit)
                options=SearchOptions(4 if args.max_depth is None else args.max_depth,20000 if args.tt_capacity is None else args.tt_capacity,not args.no_ordering)
                if config.quick_depth>options.max_depth:raise ValueError("Quick depth cannot exceed final depth")
                initial_weights,initial_source=load_initial_weights(args,config)
                record_search=args.record_search
                hashes={};seen=set()
                for filename,count,seed in (("quick_openings.json",config.quick_pairs,config.seed),("selection_openings.json",config.final_pairs,config.seed+1)):
                    data=generate_openings(count,seed)
                    boards={tuple(map(tuple,e["board"])) for e in data["openings"]}
                    if boards&seen:raise ValueError("Quick/final openings overlap; choose a different seed")
                    seen|=boards
                    path=directory/filename;path.write_text(json.dumps(data),encoding="utf-8");hashes[filename]=hashlib.sha256(path.read_bytes()).hexdigest()
                population=initial_population(config,seed_weights=initial_weights)
                checkpoint=dict(schema_version=2,generation=0,config=asdict(config),search_options=asdict(options),
                                opening_hashes=hashes,population=population,population_stats=population_report(population),
                                initial_weights=list(initial_weights) if initial_weights is not None else None,
                                initial_weights_source=initial_source,record_search=record_search,
                                best=(dict(weights=list(initial_weights),generation=0,fitness=None,points=None,source=initial_source)
                                      if initial_weights is not None else None),
                                source_hash=source_hash(),source_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,encoding="utf-8").strip(),
                                source_changes=subprocess.check_output(["git","status","--porcelain","--","."],cwd=ROOT,encoding="utf-8"))
                save_checkpoint(directory,checkpoint)
            export_best(directory,checkpoint)
            for _ in range(args.generations):
                if (directory/"STOP").exists():print("STOP requested",flush=True);break
                generation=checkpoint["generation"]+1
                previous=checkpoint["best"]
                ranked,screening=run_generation(directory,checkpoint["population"],generation,options,config.seed,config=config,incumbent=previous,record_search=record_search)
                # A changed opponent pool makes past scores incomparable. The incumbent
                # is re-tested; this generation's best is selected from current final matches.
                best=dict(ranked[0],generation=generation)
                population=next_population([t["weights"] for t in ranked],config,generation,
                                           incumbent=previous["weights"] if previous else None)
                retention=dict(baseline_present=any(tuple(w)==BASE_WEIGHTS for w in population),
                               previous_champion_present=bool(previous) and any(tuple(w)==tuple(previous["weights"]) for w in population))
                checkpoint=dict(checkpoint,generation=generation,trials=ranked,screening=screening,best=best,
                                population=population,population_stats=population_report(population),
                                population_retention=retention,record_search=record_search)
                save_checkpoint(directory,checkpoint);export_best(directory,checkpoint)
                print(f"Checkpoint {generation}: current-pool best fitness {best['fitness']:.3f}; official points {best['points']}; "
                      f"population distinct {checkpoint['population_stats']['distinct']}/{config.population}",flush=True)
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:
        parser.exit(1,f"Evolution stopped: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130,"Interrupted; resume from the last completed generation.\n")

if __name__=="__main__":main()
