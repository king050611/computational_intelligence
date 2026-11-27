"""Build isolated Phase 2 strategy datasets from validated internal replays."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from time import perf_counter
from config.experimental import SearchOptions
from src.enhanced_search import choose_enhanced
from hashlib import sha256
import json
from pathlib import Path

from scripts.analyze_history import normalize_replay, write_jsonl
from scripts.analyze_positions import analyze_game, reference
from src.evaluation import load_evaluator
from src.features import extract_features
from src.game import get_legal_moves


def symmetry(board, side):
    forms=[]
    grid=tuple(map(tuple,board))
    for _ in range(4):
        forms.extend(("".join("".join(row) for row in grid),
                      "".join("".join(reversed(row)) for row in grid)))
        grid=tuple(zip(*grid[::-1]))
    return side,min(forms)


def read_rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--external",type=Path,action="append",default=[],help="Already validated A-class JSONL")
    args=parser.parse_args()
    historical=Path("reports/historical_analysis")
    model=load_evaluator(historical/"v4_champion_schema2.json")
    games=[g for g in read_rows(historical/"historical_games.jsonl") if g["quality"]=="complete"]
    rejected=[]
    for path in sorted([*historical.glob("paired_validation/*/games.json"),
                        *Path("data/internal").glob("*/*/games.json")]):
        data=json.loads(path.read_bytes())
        for g in data["games"]:
            valid,error=normalize_replay(g)
            if not valid or g.get("fault"):
                rejected.append(dict(source=path.as_posix(),game=g["game"],reason=error or "referee fault"))
                continue
            g=deepcopy(g)
            elapsed={"A":0.0,"D":0.0}
            for event in g["moves"]:
                side=event["player"]
                event["remaining_game_seconds_before"]=max(0.0,60-elapsed[side])
                elapsed[side]+=event.get("elapsed_seconds",0.0)
            games.append(dict(g,repetition_history_rule="reconstruct from initial_board and ordered moves",game_id=f"{path.as_posix()}:{g['game']}",experiment=path.as_posix(),
                              version="V6",winner=g["result"]["winner"],termination=g["result"]["reason"],
                              mode=data.get("mode","standard_games")))
    for path in args.external:
        for row in read_rows(path):
            if row["classification"]!="A" or not row["source"].get("research_use_authorized"):
                raise ValueError("Only authorized A-class games can enter the exact dataset")
            end=row["course_result"]
            games.append(dict(game_id=f"{row['source']['url']}:{row['game_id']}",experiment=path.as_posix(),
                              initial_board=row["initial_board"],moves=row["moves"],our_side=None,
                              winner=end["winner"],termination=end["reason"],version="external",mode="external_human"))
    args.output.mkdir(parents=True,exist_ok=False)
    frozen={symmetry(g["board"],g["side"]) for g in read_rows(Path("data/positions/holdout_positions.jsonl"))}
    # Also reserve every board from Phase 1 holdout games.
    old_games={g["game_id"] for g in read_rows(Path("data/positions/holdout_positions.jsonl"))}
    for game in games:
        if game["game_id"] in old_games:
            frozen.update(symmetry(m["board_before"],m["player"]) for m in game["moves"])
    all_seen=set()
    selected=[]
    buckets=defaultdict(list)
    stage=defaultdict(Counter)
    field=defaultdict(list)
    assigned=Counter()
    fingerprints=set()
    for game in games:
        identity=json.dumps([game["initial_board"],[m["move"] for m in game["moves"]],
                            game["winner"],game.get("attacker_seconds"),game.get("defender_seconds")])
        if identity in fingerprints:
            continue
        fingerprints.add(identity)
        selected.append(game)
        mode=game.get("mode","historical")
        stage[mode][game["winner"]]+=1
        if game["game_id"] in old_games:
            continue
        outcome=game["winner"]
        for move in game["moves"]:
            f=extract_features(move["board_before"])
            field[mode,outcome].append(f)
        slot=int(sha256(game["game_id"].encode()).hexdigest()[:12],16)%100
        split="development" if slot<70 else "regression" if slot<85 else "holdout"
        assigned[split]+=1
        for case in analyze_game(game,model):
            key=symmetry(case["board"],case["side"])
            if key in frozen or key in all_seen:
                continue
            all_seen.add(key)
            case["rule_compatibility"]="A"
            case["source_kind"]="external_human" if mode=="external_human" else "internal_ai"
            case["search_mode"]=mode
            case["legal_moves"]=get_legal_moves(case["board"],case["side"])
            case["confidence"]="verified_one_ply" if any(x in case["categories"] for x in
                 ("king_captured","king_escaped","avoidable_mate_in_one","missed_immediate_win")) else "descriptive"
            buckets[split].append(case)
    write_jsonl(args.output/"exact_games.jsonl",selected)
    for split in ("development","regression","holdout"):
        for case in buckets[split]:
            stats={}
            recommendation=choose_enhanced(case["board"],case["side"],deadline=perf_counter()+0.4,
                history=case["history"],evaluator=model,options=SearchOptions(max_depth=4),stats=stats)
            case["current_ai"]=dict(move=recommendation,score=stats["score"],
                                    completed_depth=stats["completed_depth"],seconds_cap=0.4)
            case["reference"]=reference(case,model)
        write_jsonl(args.output/f"{split}_positions.jsonl",buckets[split])
    stats=dict(games=len(selected),modes=stage,rejected=rejected,positions={k:len(v) for k,v in buckets.items()},
               assigned_games=assigned, external_games=sum(g.get("mode")=="external_human" for g in selected), reserved_holdout_board_orbits=len(frozen),
               categories=Counter(c for rows in buckets.values() for row in rows for c in row["categories"]),
               feature_means={f"{mode}/{outcome}":dict(moves=len(values),
                   means=[sum(row[i] for row in values)/len(values) for i in range(8)])
                   for (mode,outcome),values in field.items()})
    (args.output/"metrics.json").write_text(json.dumps(stats,indent=2),encoding="utf-8")
    print(json.dumps(stats))


if __name__=="__main__":
    main()
