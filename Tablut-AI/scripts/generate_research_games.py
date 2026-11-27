"""Generate a small reproducible Phase 2 internal replay batch."""
import json
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict
from hashlib import sha256
import subprocess
from scripts.validate_v6 import play, historical_openings
from scripts.generate_openings import generate_openings
from scripts.replay_demo import write_replay
from config.experimental import SearchOptions
from src.evaluation import load_evaluator, WeightedEvaluator
from config.evolution import BASE_WEIGHTS

def main():
    commit=subprocess.check_output(["git","rev-parse","HEAD"],encoding="utf-8").strip()
    model_sha=sha256(Path("reports/historical_analysis/v4_champion_schema2.json").read_bytes()).hexdigest()
    model=load_evaluator("reports/historical_analysis/v4_champion_schema2.json")
    known=historical_openings()
    for mode,seed in (("standard_games",79173),("high_budget_games",79174)):
        options=SearchOptions(max_depth=4) if mode=="standard_games" else SearchOptions(max_depth=5,node_budget=30000)
        control=WeightedEvaluator(BASE_WEIGHTS)
        out=Path("data/internal")/mode/"phase2_pilot"
        out.mkdir(parents=True,exist_ok=False)
        entries=generate_openings(2,seed)["openings"]
        rows=[]
        for entry in entries:
            board=tuple(map(tuple,entry["board"]))
            assert board not in known
            known.add(board)
            for side in ("A","D"):
                row=play(entry,side,model,options,control,options)
                row.update(game=len(rows)+1,seed=seed)
                rows.append(row)
                with (out/"progress.jsonl").open("a",encoding="utf-8") as log:
                    log.write(json.dumps(row)+"\n")
                print(mode,entry["id"],side,row["result"],flush=True)
        for row in rows:
            spent={"A":0.0,"D":0.0}
            for event in row["moves"]:
                side=event["player"]
                event["remaining_game_seconds_before"]=max(0.0,60-spent[side])
                spent[side]+=event.get("elapsed_seconds",0.0)
        write_replay(dict(schema_version="1.1",created_at=datetime.now(timezone.utc).isoformat(),
            games=rows,mode=mode,options=asdict(options),candidate_weights=model.weights,
            control_weights=control.weights,source_commit=commit,model_sha256=model_sha),out)


if __name__=="__main__":
    main()
