"""Summarize validated Phase 3 games, including completed games in partial batches."""
from collections import Counter
import json
from hashlib import sha256
from pathlib import Path

from scripts.analyze_history import normalize_replay, write_jsonl
from scripts.build_strategy_dataset import read_rows, symmetry
from scripts.analyze_positions import analyze_game
from src.evaluation import load_evaluator

def main():
    root=Path("reports/phase3")
    exact=read_rows(Path("data/positions/phase2/exact_games.jsonl"))
    evaluator=load_evaluator("reports/historical_analysis/v4_champion_schema2.json")
    results={}
    new_splits=[]
    reserved={symmetry(r["board"],r["side"]) for p in Path("data/positions").rglob("*holdout*_positions.jsonl") for r in read_rows(p)}
    for folder in sorted((root/"matches").glob("*")):
        manifest=json.loads((folder/"manifest.json").read_bytes())
        records=[]
        counts=Counter()
        roles={}
        for p in sorted((folder/"individual").glob("*.json")):
            row=json.loads(p.read_bytes())
            if not normalize_replay(row)[0]:
                raise ValueError(f"Failed replay validation: {p}")
            role=row["our_side"]
            winner=row["result"]["winner"]
            result="draw" if winner=="DRAW" else "win" if winner==role else "loss"
            roles.setdefault(role,Counter())[result]+=1
            counts[result]+=1
            record=dict(row,game_id=f"phase3/{folder.name}/{row['game']}",experiment=p.as_posix(),
                        winner=winner,termination=row["result"]["reason"],mode=manifest["mode"],version="V6 study")
            _, orbit=symmetry(row["initial_board"],"A")
            slot=int(sha256(orbit.encode()).hexdigest()[:12],16)%100
            if any(symmetry(event["board_before"],event["player"]) in reserved for event in row["moves"]):
                # Flag position overlap separately; the paired opening seed still
                # determines the group, so reverse-role games cannot be separated.
                record["overlaps_previous_holdout"]=True
            split="development" if slot<70 else "regression" if slot<85 else "holdout"
            new_splits.append(dict(game_id=record["game_id"],opening_orbit_sha256=sha256(orbit.encode()).hexdigest(),
                                   split=split,overlaps_previous_holdout=record.get("overlaps_previous_holdout",False)))
            records.append(record)
        results[folder.name]=dict(games=len(records),planned=len(manifest["openings"])*(1 if manifest["candidate_side"] else 2),
            mode=manifest["mode"],results=counts,roles=roles,
            tactical=Counter(tag for row in records for case in analyze_game(row,evaluator) for tag in case["categories"]),
            max_seconds=max((max(r["attacker_seconds"],r["defender_seconds"]) for r in records),default=0))
        exact.extend(records)
    write_jsonl(root/"exact_games_snapshot.jsonl",exact)
    write_jsonl(root/"game_splits.jsonl",new_splits)
    positions=read_rows(Path("data/positions/phase3/tactical_positions.jsonl"))
    summary=dict(previous_games=62,combined_games=len(exact),matrix=results,
                 synthetic_categories=Counter(r["category"] for r in positions))
    (root/"metrics.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary))

if __name__=="__main__":
    main()
