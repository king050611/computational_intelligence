"""Paired, wall-clock V6 diagnostics with full referee replays."""
import argparse
import contextlib
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.experimental import SearchOptions
from scripts.generate_openings import generate_openings
from scripts.replay_demo import ObservedPlayer, Recorder, snapshot, write_replay
from src.evaluation import WeightedEvaluator, load_evaluator
from src.experimental_player import ExperimentalPlayer


def play(entry, side, model, options, control, control_options):
    game = Recorder()
    game.board = snapshot(entry["board"])
    game.initial_board = snapshot(game.board)
    bots = [ExperimentalPlayer("evolutionary_dynamic", opening=game.initial_board,
                               evaluator=evaluator, options=opts, record_search=True)
            for evaluator, opts in ((model, options), (control, control_options))]
    ours, other = (ObservedPlayer(bot, game, label) for bot, label in zip(bots, ("candidate", "control")))
    attacker, defender = (ours, other) if side == "A" else (other, ours)
    with contextlib.redirect_stdout(io.StringIO()) as log:
        game.play(attacker, defender)
    message = log.getvalue()
    seconds = [sum(bot.timed.times) for bot in (attacker, defender)]
    issue = (game.termination is None or max(seconds) > 60 or
             any(bot.timed.errors or bot.timed.invalid_returns for bot in (attacker, defender)))
    if issue and game.pending is not None:
        game.pending.update(accepted=False, status="fault", board_after=snapshot(game.board))
        game.events.append(game.pending)
    peak = game.termination or {"winner": game.winner, "reason": "fault"}
    return dict(opening_id=entry["id"], our_side=side, winner=peak["winner"], result=peak,
                strategies=dict(A=attacker.strategy, D=defender.strategy),
                initial_board=game.initial_board, final_board=snapshot(game.board),
                moves=game.events, accepted_moves=sum(m.get("accepted", False) for m in game.events),
                attacker_seconds=seconds[0], defender_seconds=seconds[1], referee_log=message,
                fault=issue, points=1 if peak["winner"]=="DRAW" else 2 if peak["winner"]==side else 0)


def boards(entries):
    return {tuple(map(tuple, entry["board"])) for entry in entries}


def historical_openings():
    blocked = set()
    reports = ROOT/"reports"
    historical = (reports/"training", reports/"experiments", reports/"replays")
    for file in (path for folder in historical for path in folder.rglob("*openings*.json")):
        try:
            data=json.loads(file.read_bytes())
            if isinstance(data,dict) and isinstance(data.get("openings"),list):
                blocked.update(boards(data["openings"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for line in (ROOT/"reports/historical_analysis/historical_games.jsonl").read_text(encoding="utf-8").splitlines():
        board=json.loads(line).get("initial_board")
        if board:
            blocked.add(tuple(map(tuple,board)))
    return blocked


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy-pairs", type=int, default=4)
    parser.add_argument("--feature-pairs", type=int, default=2)
    args=parser.parse_args()
    if min(args.policy_pairs,args.feature_pairs)<1:
        parser.error("Positive paired sample sizes are required")
    args.output.mkdir(parents=True,exist_ok=False)
    source=ROOT/"reports/historical_analysis/v4_champion_schema2.json"
    model=load_evaluator(source)
    full=WeightedEvaluator(model.weights[:6]+(-80,-80))
    without_w7=WeightedEvaluator(full.weights[:6]+(0,-80))
    without_w8=WeightedEvaluator(full.weights[:6]+(-80,0))
    on=SearchOptions(max_depth=4, draw_policy=True)
    off=replace(on,draw_policy=False)
    excluded=historical_openings()
    policy=generate_openings(args.policy_pairs,63167)
    assert not boards(policy["openings"]) & excluded
    feature=generate_openings(args.feature_pairs,19873)
    assert not boards(feature["openings"]) & (excluded | boards(policy["openings"]))
    manifest=dict(model_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), model_weights=model.weights,
                  feature_weights=full.weights, policy_seed=63167, feature_seed=19873, historical_overlap=0,
                  max_depth=4, tt_capacity=on.tt_capacity, order_moves=True, node_budget=0,
                  created_at=datetime.now(timezone.utc).isoformat())
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    arms=(("draw_v5_order",policy,model,off),("draw_v6_order",policy,model,on),
          ("feature_full",feature,full,off),("feature_without_w7",feature,without_w7,off),
          ("feature_without_w8",feature,without_w8,off))
    for name, suite, candidate, options in arms:
        (args.output/f"{name}_openings.json").write_text(json.dumps(suite),encoding="utf-8")
    # Interleave arms on the same board and role to limit time-of-run confounding.
    results={name:[] for name, *_ in arms}
    for suite, group in ((policy,arms[:2]),(feature,arms[2:])):
        for entry in suite["openings"]:
            for side in ("A","D"):
                for name,_,candidate,options in group:
                    row=play(entry,side,candidate,options,model,off)
                    row.update(game=len(results[name])+1, seed=suite["seed"])
                    results[name].append(row)
                    with (args.output/f"{name}.jsonl").open("a",encoding="utf-8") as log:
                        log.write(json.dumps(row,separators=(",",":"))+"\n")
                    print(name,entry["id"],side,row["result"],flush=True)
                    if row["fault"]:
                        raise RuntimeError(f"Referee fault in {name}, opening {entry['id']}, side {side}")
        for name, *_ in group:
            write_replay(dict(schema_version="1.1",created_at=manifest["created_at"],games=results[name]),
                         args.output/name)
    print("V6 experiment completed",flush=True)


if __name__=="__main__":
    main()
