"""Run and summarize matched, fixed-attacker V7 strategy experiments."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("screen", "confirm"), default="screen")
    parser.add_argument("--finalist", choices=("A1", "A2", "A3"))
    parser.add_argument("--output", type=Path, default=Path("reports/v7_attacker"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if (args.stage == "confirm") != bool(args.finalist):
        parser.error("Confirmation requires exactly one frozen finalist")

    screen = args.stage == "screen"
    strategies = ("A0", "A1", "A2", "A3") if screen else ("A0", args.finalist)
    opponents = ("champion", "escape", "protective")
    quotas = (6, 5, 5) if screen else (14, 13, 13)
    seed = 78421 if screen else 88421
    models = Path("reports/phase4/models")
    base = models / "champion.json"
    out = args.output / args.stage
    report = {}
    for strategy in strategies:
        result = Counter()
        by_opponent = {}
        for i, (opponent, games) in enumerate(zip(opponents, quotas)):
            target = out / strategy / opponent
            command = [sys.executable, "-u", "-m", "scripts.generate_research_games",
                       "--pairs", str(games), "--candidate-side", "A", "--seed", str(seed+i),
                       "--candidate-model", str(base), "--control-model", str(models / f"{opponent}.json"),
                       "--output", str(target)]
            if strategy != "A0":
                command.extend(["--attacker-strategy", strategy])
            if args.resume and (target / "manifest.json").exists():
                command.append("--resume")
            subprocess.run(command, check=True)
            rows = [json.loads(p.read_bytes()) for p in sorted((target / "individual").glob("*.json"))]
            if len(rows) != games:
                raise RuntimeError(f"Incomplete suite: {target}")
            counts = Counter(row["result"]["winner"] for row in rows)
            result.update(counts)
            by_opponent[opponent] = dict(wins=counts["A"], draws=counts["DRAW"], losses=counts["D"],
                                        max_attacker_seconds=max(row["attacker_seconds"] for row in rows))
        report[strategy] = dict(wins=result["A"], draws=result["DRAW"], losses=result["D"],
                                points=2*result["A"]+result["DRAW"], opponents=by_opponent)
    (out / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
