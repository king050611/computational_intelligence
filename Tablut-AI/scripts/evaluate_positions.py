"""Compare exact fixed-depth scores, nodes and wall time on matched positions."""
import argparse
import json
from math import inf
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.experimental import SearchOptions
from scripts.generate_openings import generate_openings
from src.enhanced_search import EnhancedSearch, evaluate
from src.game import apply_move, get_legal_moves, parse_board
from src.search import alpha_beta


def compare(count, depth, seed):
    positions = generate_openings(count, seed)["openings"]
    results = []
    for index, entry in enumerate(positions):
        board = parse_board(entry["board"])
        side = "A" if index % 2 == 0 else "D"
        if side == "D":
            board = apply_move(board, get_legal_moves(board, "A")[0], "A")
        scores, stats = {}, {}
        implementations = ("legacy", "plain", "ordered", "hinted")
        for mode in implementations:
            start = perf_counter()
            counter = dict(nodes=0, cutoffs=0, tt_hint_hits=0)
            if mode == "legacy":
                score = alpha_beta(board, side, side, depth, -inf, inf, inf, stats=counter)
            else:
                options = SearchOptions(depth, 20_000 if mode == "hinted" else 0, mode != "plain")
                search = EnhancedSearch(side, inf, evaluate, options, counter)
                score, _ = search.visit(board, side, depth, -inf, inf, ())
            seconds = perf_counter() - start
            scores[mode] = score
            stats[mode] = dict(**counter, seconds=seconds, nodes_per_second=counter["nodes"] / seconds)
        if len(set(scores.values())) != 1:
            raise AssertionError(f"Position {entry['id']} ({side}) disagrees: {scores}")
        results.append(dict(id=entry["id"], side=side, score=scores["legacy"], stats=stats))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=100)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.positions, args.depth) < 1 or args.output.exists():
        parser.error("Positive position count/depth and a new output path are required")
    results = compare(args.positions, args.depth, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(dict(depth=args.depth, seed=args.seed, results=results), file, indent=2)
    for mode in results[0]["stats"]:
        nodes = sum(row["stats"][mode]["nodes"] for row in results)
        seconds = sum(row["stats"][mode]["seconds"] for row in results)
        slower = sum(row["stats"][mode]["seconds"] > row["stats"]["legacy"]["seconds"] for row in results)
        print(f"{mode}: {nodes} nodes, {seconds:.3f}s, {nodes / seconds:.0f} nodes/s, {slower} slower positions")
    print(f"Exact scores agree on {len(results)} positions at depth {args.depth}")


if __name__ == "__main__":
    main()
