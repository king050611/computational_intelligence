"""Summarize the V7 fixed-attacker experiments from validated local replays."""
import argparse
from collections import Counter
import json
from pathlib import Path
from random import Random
from statistics import mean

from scripts.analyze_history import normalize_replay
from scripts.build_strategy_dataset import symmetry
from src.blockade import capture_score, control_score


def summarize(rows):
    wins = Counter(row["result"]["winner"] for row in rows)
    metrics = Counter()
    depths, durations, search_times = [], [], []
    for row in rows:
        controlled = False
        for move in row["moves"]:
            if move["player"] != "A":
                continue
            board = tuple(map(tuple, move["board_before"]))
            if control_score(board) >= .75:
                controlled = True
                metrics["controlled_decisions"] += 1
                if capture_score(board, detailed=False) >= .5:
                    metrics["capture_ready_controlled_decisions"] += 1
            metrics["attacker_decisions"] += 1
            durations.append(move["elapsed_seconds"])
            search = move.get("search") or {}
            if "completed_depth" in search:
                depths.append(search["completed_depth"])
                if "elapsed_seconds" in search:
                    search_times.append(search["elapsed_seconds"])
                metrics["search_budget_cutoffs"] += int(search.get("timed_out", False))
        metrics["games_with_control"] += controlled
        metrics["captures_after_control"] += controlled and row["result"]["reason"] == "king_captured"
    n = len(rows)
    return dict(games=n, wins=wins["A"], draws=wins["DRAW"], losses=wins["D"],
                win_rate=wins["A"]/n, draw_rate=wins["DRAW"]/n, loss_rate=wins["D"]/n,
                point_rate=(2*wins["A"]+wins["DRAW"])/(2*n), **metrics,
                average_depth=mean(depths) if depths else None, depth_samples=len(depths),
                average_outer_seconds=mean(durations),
                average_search_seconds=mean(search_times) if search_times else None,
                max_attacker_seconds=max(row["attacker_seconds"] for row in rows),
                max_defender_seconds=max(row["defender_seconds"] for row in rows))


def paired(base, model):
    changes = Counter()
    groups = {}
    points = {"A": 2, "DRAW": 1, "D": 0}
    if base.keys() != model.keys():
        raise ValueError("Opening/opponent pairs differ")
    for key, row in base.items():
        earlier, later = row["result"]["winner"], model[key]["result"]["winner"]
        changes[f"{earlier}->{later}"] += 1
        groups.setdefault(key[0], []).append((int(later == "A")-int(earlier == "A"),
                                            (points[later]-points[earlier])/2))
    rng = Random(78421)
    size = len(base)
    boot = [[], []]
    for _ in range(5000):
        sample = [item for group in groups.values() for item in rng.choices(group, k=len(group))]
        for i in range(2):
            boot[i].append(sum(item[i] for item in sample)/size)
    limits = [(sorted(values)[125], sorted(values)[4874]) for values in boot]
    return dict(outcome_changes=changes, win_rate_ci95=limits[0], point_rate_ci95=limits[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage_dir", type=Path)
    args = parser.parse_args()
    root = args.stage_dir
    planned = json.loads((root / "summary.json").read_bytes())
    offenders = list(root.glob("A*/**/rejected/*.json"))
    if offenders:
        raise ValueError(f"{len(offenders)} referee faults in {root}; inspect rejected replays")
    report, grouped = {}, {}
    for strategy, expected in planned.items():
        strategy_rows = {}
        by_opponent = {}
        for opponent, counts in expected["opponents"].items():
            folder = root / strategy / opponent
            rows = [json.loads(path.read_bytes()) for path in sorted(folder.glob("individual/????.json"))]
            if len(rows) != counts["wins"] + counts["draws"] + counts["losses"]:
                raise ValueError(f"Incomplete match suite: {folder}")
            by_opponent[opponent] = summarize(rows)
            for row in rows:
                if not normalize_replay(row)[0] or row["our_side"] != "A":
                    raise ValueError(f"Invalid replay in {folder}")
                if max(row["attacker_seconds"], row["defender_seconds"]) > 60:
                    raise ValueError(f"Referee clock exceeded in {folder}")
                raw_board = tuple(map(tuple, row["initial_board"]))
                key = (opponent, row["opening_id"], raw_board)
                if key in strategy_rows:
                    raise ValueError(f"Duplicate opening in {folder}")
                strategy_rows[key] = row
        grouped[strategy] = strategy_rows
        report[strategy] = dict(summarize(list(strategy_rows.values())), opponents=by_opponent,
                                referee_timeouts=0, illegal_moves=0)
    for strategy in report:
        if strategy != "A0":
            report[strategy]["paired_vs_A0"] = paired(grouped["A0"], grouped[strategy])
    report["unique_openings_up_to_symmetry"] = len({
        symmetry(key[2], "A") for key in grouped["A0"]
    })
    with (root / "analysis.json").open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
    print(json.dumps({k: v["wins"] for k, v in report.items() if isinstance(v, dict)}))


if __name__ == "__main__":
    main()
