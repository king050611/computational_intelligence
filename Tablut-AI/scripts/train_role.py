"""Fixed-role evolutionary training using the Phase 3 replay runner."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from hashlib import sha256
from math import isfinite
from pathlib import Path
from random import Random
import sys

from config.evolution import BASE_WEIGHTS, EvolutionConfig
from scripts.build_strategy_dataset import symmetry, read_rows
from scripts.evaluate_tactics import evaluate_cases
from src.evaluation import WeightedEvaluator
from scripts.generate_openings import generate_openings
from scripts.generate_research_games import ROOT, MatchFault, fingerprint, play_job
from scripts.replay_demo import write_replay
from scripts.analyze_history import normalize_replay
from scripts.train_evolution import publish
from src.evaluation import load_evaluator, model_record
from src.evolution import mutate_distinct, next_population, project, save_checkpoint, training_lock


def allocate(pool,count):
    total=sum(item["share"] for item in pool)
    quotas=[count*item["share"]/total for item in pool]
    numbers=[int(q) for q in quotas]
    for i in sorted(range(len(pool)),key=lambda i:quotas[i]-numbers[i],reverse=True)[:count-sum(numbers)]:
        numbers[i]+=1
    return [i for i,n in enumerate(numbers) for _ in range(n)]


def rank(trial,mode):
    return ((trial["wins"],trial["points"]) if mode=="win-first"
            else (trial["reward"],trial["points"],trial["wins"]))


def summarize(rows, side):
    if not rows or any(r["our_side"]!=side for r in rows):
        raise ValueError("Incomplete or mixed-role suite")
    outcomes=Counter(r["result"]["winner"] for r in rows)
    wins,draws=outcomes[side],outcomes["DRAW"]
    return dict(games=len(rows),wins=wins,draws=draws,losses=len(rows)-wins-draws,
                points=2*wins+draws,reward=3*wins+draws,fitness=(3*wins+draws)/(3*len(rows)))


def population(seed,styles,config):
    initial=list(dict.fromkeys([seed,BASE_WEIGHTS,*styles]))
    rng=Random(config.seed)
    for style in styles[:2]:
        child=project(tuple(rng.choice((a,b)) for a,b in zip(seed,style)),config)
        if child not in initial:
            initial.append(child)
    while len(initial)<config.population:
        initial.append(mutate_distinct(seed,initial,rng,config))
    return initial[:config.population]


def model_spec(engine,model,depth,seconds):
    engine=Path(engine).resolve()
    files=fingerprint(engine)
    if not files or depth<1 or not 5<seconds<=60:
        raise ValueError("Invalid engine or formal search budget")
    if model:
        model=Path(model).resolve()
        load_evaluator(model)
    return dict(engine=str(engine),files=files,model=str(model) if model else None,
                model_sha256=sha256(model.read_bytes()).hexdigest() if model else None,
                depth=depth,nodes=0,seconds=seconds)


def suite(out,weights,side,entries,depth,pool,seed,candidate_engine=None):
    out.mkdir(parents=True,exist_ok=True)
    model=out/"model.json"
    if model.exists():
        if load_evaluator(model).weights!=tuple(weights):
            raise ValueError("Saved candidate weights differ")
    else:
        publish(model,model_record(weights,training_side=side))
    candidate=model_spec(candidate_engine or ROOT,model,depth,60)
    rows=[]
    for index,(entry,opponent) in enumerate(zip(entries,allocate(pool,len(entries))),1):
        path=out/f"{index:04d}.json"
        control=pool[opponent]["spec"]
        if path.exists():
            row=json.loads(path.read_bytes())
            if (not normalize_replay(row)[0] or row["initial_board"]!=entry["board"]
                    or row["our_side"]!=side or row["opening_id"]!=entry["id"]):
                raise ValueError(f"Saved role replay does not match suite: {path}")
        else:
            rejected=path.parent/"rejected"/path.name
            if rejected.exists():
                fault=json.loads(rejected.read_bytes())
                raise MatchFault(f"Saved referee fault: {rejected}",fault["faulty_sides"])
            row=play_job((path,entry,side,[candidate,control],60,seed))
        rows.append(row)
    write_replay(dict(schema_version="1.1",games=rows),out)
    result=dict(summarize(rows,side),weights=weights)
    print(out.name,result,flush=True)
    return result


def main(role,argv):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opponent-pool",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--ranking-mode",choices=("fitness","win-first"),default="win-first")
    parser.add_argument("--initial-model",type=Path,default=ROOT/"reports/historical_analysis/v4_champion_schema2.json")
    parser.add_argument("--candidate-engine",type=Path,default=ROOT,
                        help="Frozen engine directory for the candidate role (defaults to the workspace)")
    parser.add_argument("--style-model",type=Path,action="append",default=[])
    parser.add_argument("--quick-games",type=int,default=4)
    parser.add_argument("--final-games",type=int,default=12)
    parser.add_argument("--quick-depth",type=int,default=3)
    parser.add_argument("--max-depth",type=int,default=4)
    parser.add_argument("--generations",type=int,default=1)
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--resume",action="store_true")
    parser.add_argument("--tactics-dir",type=Path)
    args=parser.parse_args(argv)
    if min(args.quick_games,args.final_games,args.quick_depth,args.max_depth,args.generations)<1:
        parser.error("Counts and depths must be positive")
    side="A" if role=="attacker" else "D"
    config=EvolutionConfig(population=8,elite=2,sigma=40,bound=1000,seed=args.seed,constrained=False)
    models=[load_evaluator(path) for path in [args.initial_model,*args.style_model]]
    if any(not isinstance(model,WeightedEvaluator) for model in models):
        parser.error("Initial and style models must each contain one weight vector")
    initial=models[0].weights
    if any(abs(w)>config.bound for w in initial):
        parser.error("Initial model exceeds experimental bounds")
    style_weights=[model.weights for model in models[1:]]
    if len(style_weights)>2 or any(abs(w)>config.bound for row in style_weights for w in row):
        parser.error("Supply up to two styles within weight bounds")
    pool=[]
    for item in json.loads(args.opponent_pool.read_bytes()):
        if item["side"]==side or item["side"] not in ("A","D") or not isfinite(item["share"]) or item["share"]<=0:
            parser.error("Opponents must have the opposite role and a positive share")
        resolve=lambda path: args.opponent_pool.parent/path
        spec=model_spec(resolve(item.get("engine",str(ROOT))),resolve(item["model"]) if item.get("model") else None,
                        item.get("depth",4),item.get("seconds",60))
        if item.get("model_sha256",spec["model_sha256"])!=spec["model_sha256"] or item.get("files",spec["files"])!=spec["files"]:
            parser.error("Opponent does not match declared hashes")
        pool.append(dict(name=item["name"],share=item["share"],spec=spec))
    if not pool or len({i["name"] for i in pool})!=len(pool):
        parser.error("An opponent pool with unique names is required")
    reserved=set()
    for path in (ROOT/"data/positions").rglob("*holdout*_positions.jsonl"):
        for line in path.read_bytes().splitlines():
            row=json.loads(line)
            reserved.add(symmetry(row["board"],row["side"]))
    entries=[]
    count=args.quick_games+args.final_games
    for entry in generate_openings(count*2,args.seed)["openings"]:
        key=symmetry(entry["board"],"A")
        if key not in reserved:
            reserved.add(key)
            entries.append(entry)
            if len(entries)==count:
                break
    if len(entries)!=count:
        parser.error("Insufficient disjoint openings")
    tactical={}
    if args.tactics_dir:
        for split in ("development","regression"):
            path=args.tactics_dir/f"{split}.jsonl"
            tactical[split]=(read_rows(path),sha256(path.read_bytes()).hexdigest())
    provenance={Path(f).name:sha256(Path(f).read_bytes()).hexdigest()
                for f in (__file__,ROOT/"scripts/generate_research_games.py",ROOT/"scripts/evaluate_tactics.py",ROOT/"reference/Tablut.py")}
    candidate_engine=args.candidate_engine.resolve()
    manifest=json.loads(json.dumps(dict(role=role,pool=pool,config=asdict(config),initial=initial,
        candidate_engine=dict(path=str(candidate_engine),files=fingerprint(candidate_engine)),
        styles=style_weights,openings=entries,quick_games=args.quick_games,quick_depth=args.quick_depth,
        final_depth=args.max_depth,ranking=args.ranking_mode,tactics={k:v[1] for k,v in tactical.items()},source=fingerprint(ROOT),provenance=provenance)))
    entries=manifest["openings"]
    out=args.output_dir
    out.mkdir(parents=True,exist_ok=True)
    with training_lock(out):
        path=out/"config.json"
        if args.resume:
            if not path.is_file() or json.loads(path.read_bytes())!=manifest:
                raise ValueError("Resume requires identical role, source, pool, openings and settings")
            checkpoint=json.loads(sorted(out.glob("checkpoint-*.json"))[-1].read_bytes())
        else:
            if path.exists():
                raise ValueError("Existing run. Use --resume")
            publish(path,manifest)
            checkpoint=dict(generation=0,population=population(initial,style_weights,config),best=initial)
            save_checkpoint(out,checkpoint)
        baseline=tuple(checkpoint["best"])
        for generation in range(checkpoint["generation"]+1,checkpoint["generation"]+1+args.generations):
            if (out/"STOP").exists():
                break
            folder=out/f"g{generation:04}"
            quick=entries[:args.quick_games]
            final=entries[args.quick_games:]
            weights=[tuple(w) for w in checkpoint["population"]]
            weights=list(dict.fromkeys([baseline,*weights]))[:config.population]

            def collect(vectors,label,openings,depth):
                results=[]
                for index,vector in enumerate(vectors):
                    try:
                        trial=suite(folder/f"{label}_{index:02}",vector,side,openings,depth,pool,args.seed,
                                    candidate_engine=candidate_engine)
                        if tactical:
                            cases=[case for group,(rows,_) in tactical.items() if label=="final" or group=="development"
                                   for case in (rows if label=="final" else rows[:24]) if case["side"]==side]
                            trial["tactical"]=evaluate_cases(cases,WeightedEvaluator(tuple(vector)),depth=depth)
                            if any(stats["illegal"] for stats in trial["tactical"].values()):
                                raise MatchFault("Candidate produced an illegal tactical move",{side})
                        results.append(trial)
                    except MatchFault as exc:
                        if index==0 or exc.faulty_sides!={side}:
                            raise RuntimeError(f"Invalid control or incumbent suite {label}: {exc}") from exc
                        print(f"Excluded {label} candidate {index}: {exc}",flush=True)
                        results.append(dict(weights=vector,disqualified=True,reason=str(exc)))
                return results

            screened=collect(weights,"quick",quick,args.quick_depth)
            others=sorted((t for t in screened[1:] if not t.get("disqualified")),key=lambda t:rank(t,args.ranking_mode),reverse=True)
            finalists=[baseline,*[tuple(t["weights"]) for t in others[:3]]]
            results=collect(finalists,"final",final,args.max_depth)
            floor=results[0]["points"]
            safe=[t for t in results if not t.get("disqualified") and t["points"]>=floor]
            ranked=sorted(safe,key=lambda t:rank(t,args.ranking_mode),reverse=True)
            best=tuple(ranked[0]["weights"])
            # Parents also meet the official floor. If only the incumbent qualifies,
            # seed a fresh diverse population instead of breeding an ineligible model.
            next_weights=(next_population([t["weights"] for t in ranked],config,generation,incumbent=best)
                          if len(ranked)>=config.elite else population(best,[],config))
            checkpoint=dict(generation=generation,population=next_weights,best=best,role=role,
                            points_floor=floor,quick=screened,final=results)
            save_checkpoint(out,checkpoint)
            publish(out/f"{role}_best.json",model_record(best,training_role=role,generation=generation))
            print(f"{role} generation {generation}: {ranked[0]['wins']} wins, {ranked[0]['points']} points, floor {floor}",flush=True)
