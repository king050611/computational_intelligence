"""Run official matches, reporting outcomes and wall time. No third-party deps."""
import argparse
import contextlib
import io
import json
import sys
from pathlib import Path
from time import perf_counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Tablut import Tablut
from TeamXX import Player


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.games <= 0:
        parser.error("--games must be positive")
    results = []
    for index in range(args.games):
        game = Tablut()
        start = perf_counter()
        with contextlib.redirect_stdout(io.StringIO()) as log:
            game.play(Player(), Player())
        message = log.getvalue()
        results.append({"game": index + 1, "winner": game.winner or "DRAW",
                        "plies": game.rounds_played, "elapsed_seconds": perf_counter()-start,
                        "illegal_moves": message.count("Illegal move"),
                        "timeouts": message.count("exceeded time limit"),
                        "exceptions": message.count("Exception caught"), "log": message})
    summary = {"baseline": "deterministic first legal move vs itself",
               "games": args.games,
               "attacker_win_rate": sum(x["winner"] == "A" for x in results)/args.games,
               "defender_win_rate": sum(x["winner"] == "D" for x in results)/args.games,
               "draw_rate": sum(x["winner"] == "DRAW" for x in results)/args.games,
               "results": results}
    content = json.dumps(summary, indent=2)
    print(content)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    if any(x["illegal_moves"] or x["timeouts"] or x["exceptions"] for x in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
