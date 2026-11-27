"""Run one paired match batch and calculate a paired bootstrap interval."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from random import Random
import subprocess
import sys


def summarize(result, seed=42, samples=10_000):
    pairs = defaultdict(list)
    for game in result["results"]:
        pairs[game["opening_id"]].append(game)
    scores = []
    for opening, games in pairs.items():
        if len(games) != 2 or {game["our_side"] for game in games} != {"A", "D"}:
            raise ValueError(f"Opening {opening} is missing a role-paired game")
        scores.append(sum(game["points"] for game in games) / 4)
    if not scores:
        raise ValueError("No pairs to summarize")
    rng = Random(seed)
    size = len(scores)
    distribution = sorted(sum(rng.choices(scores, k=size)) / size for _ in range(samples))
    return dict(pairs=size, point_rate=sum(scores) / size,
                ci95=[distribution[int(0.025 * samples)], distribution[int(0.975 * samples)]],
                bootstrap_seed=seed, bootstrap_samples=samples,
                pair_points=dict(zip(pairs, scores)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--opponent", required=True)
    parser.add_argument("--openings", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--tt-capacity", type=int, default=20_000)
    parser.add_argument("--node-budget", type=int, default=0)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--opponent-model", type=Path)
    parser.add_argument("--no-ordering", action="store_true")
    parser.add_argument("--record-search", action="store_true")
    args = parser.parse_args()
    summary = args.output.with_suffix(".summary.json")
    if args.output.exists() or summary.exists():
        parser.error("Use a fresh output path")
    command = [
        sys.executable, str(Path(__file__).with_name("benchmark.py")),
        "--strategy", args.strategy, "--opponent", args.opponent,
        "--openings", str(args.openings), "--output", str(args.output),
        "--seed", str(args.seed), "--max-depth", str(args.max_depth),
        "--tt-capacity", str(args.tt_capacity),
    ]
    if args.node_budget:
        command.extend(["--node-budget", str(args.node_budget)])
    for flag,path in (("--model",args.model),("--opponent-model",args.opponent_model)):
        if path is not None:
            command.extend([flag,str(path)])
    if args.no_ordering:
        command.append("--no-ordering")
    if args.record_search:
        command.append("--record-search")
    result = subprocess.run(command)
    if result.returncode:
        return result.returncode
    stats = summarize(json.loads(args.output.read_text(encoding="utf-8")), args.seed)
    with summary.open("x", encoding="utf-8") as file:
        json.dump(stats, file, indent=2)
    print("Paired summary:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
