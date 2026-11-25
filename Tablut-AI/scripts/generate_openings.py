"""Generate reproducible, nonterminal openings with the attacker to move."""
import argparse
import json
from pathlib import Path
from random import Random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.game import apply_move, check_winner, get_legal_moves, get_state_key, initial_board


def generate_openings(count, seed):
    rng = Random(seed)
    openings, seen = [], set()
    for _ in range(count * 100):
        board, side, history, moves = initial_board(), "A", [], []
        for _ in range(rng.choice((2, 4, 6, 8))):
            move = rng.choice(get_legal_moves(board, side))
            history.append(get_state_key(board, side))
            moves.append(move)
            board = apply_move(board, move, side)
            side = "D" if side == "A" else "A"
            if check_winner(board, side, history) is not None:
                break
        else:
            if board not in seen:
                seen.add(board)
                openings.append(dict(id=len(openings) + 1, board=board, side="A", moves=moves))
                if len(openings) == count:
                    return dict(seed=seed, history_rule="restarted_opening", openings=openings)
    raise ValueError("Could not generate enough distinct legal openings")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.pairs < 1:
        parser.error("--pairs must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(generate_openings(args.pairs, args.seed), file, indent=2)


if __name__ == "__main__":
    main()
