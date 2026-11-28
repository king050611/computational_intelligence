"""Summarize referee replays and optionally rebuild their HTML view."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import mean

from scripts.replay_demo import write_replay


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Match folder, games.json, or individual replay")
    parser.add_argument("--html-dir", type=Path, help="Directory for a rebuilt replay")
    args = parser.parse_args(argv)
    path = args.input / "games.json" if args.input.is_dir() else args.input
    data = json.loads(path.read_bytes())
    rows = data["games"] if "games" in data else [data]
    summary = {}
    for side in ("A", "D"):
        entries = [row for row in rows if row.get("our_side", "A") == side]
        if not entries:
            continue
        results = Counter(row["result"].get("winner") for row in entries)
        valid = sum(results[outcome] for outcome in ("A", "D", "DRAW"))
        turns = [move for row in entries for move in row["moves"] if move["player"] == side]
        depths = [move["search"]["completed_depth"] for move in turns
                  if "completed_depth" in (move.get("search") or {})]
        times = [move["elapsed_seconds"] for move in turns if "elapsed_seconds" in move]
        clock = "attacker_seconds" if side == "A" else "defender_seconds"
        summary[side] = dict(games=len(entries), wins=results[side], draws=results["DRAW"],
            losses=valid-results[side]-results["DRAW"], win_rate=results[side]/valid if valid else None,
            point_rate=(2*results[side]+results["DRAW"])/(2*valid) if valid else None,
            average_depth=mean(depths) if depths else None, average_turn_seconds=mean(times) if times else None,
            maximum_game_seconds=max((row.get(clock,0) for row in entries), default=0),
            defeat_replays=[row.get("game", i) for i,row in enumerate(entries,1)
                            if row["result"].get("winner") in {"A","D"}-{side}])
    print(json.dumps(summary,indent=2))
    if args.html_dir:
        if "games" not in data:
            parser.error("HTML regeneration requires an official games.json bundle")
        write_replay(data,args.html_dir)


if __name__ == "__main__":
    main()
