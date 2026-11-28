"""V7 Phase 1 (P0-3/P0-4): classify blockade states and test two hypotheses.

1. Label every sampled attacker decision as effective / gap / no_structure / unstable.
2. H1: does pulling an attacker in from distance >=3 to <=2 predict a later escape?
3. H2: with the same number of adjacent attackers, do opposite-direction pairs convert?

Analysis only: nothing here is imported by the search or the evaluator.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import DIRECTIONS
from src.blockade import (adjacent_attackers, escape_reachability, immediate_escape,
                          king_moves, king_square)
from src.game import apply_move, get_legal_moves

EDGE = {0, 8}


def ray_dests(board, position):
    out = []
    r, c = position
    for dr, dc in DIRECTIONS:
        row, col = r, c
        while True:
            row += dr
            col += dc
            if not (0 <= row < 9 and 0 <= col < 9):
                break
            cell = board[row][col]
            if cell in "ADK":
                break
            if cell == ".":
                out.append((row, col))
    return out


def opposite_pairs(board):
    """Adjacent attacker pairs sitting on opposite sides of the king (capture geometry)."""
    king = king_square(board)
    if king is None:
        return 0
    r, c = king
    sides = {}
    for dr, dc in DIRECTIONS:
        ar, ac = r + dr, c + dc
        if 0 <= ar < 9 and 0 <= ac < 9 and board[ar][ac] == "A":
            sides[(dr, dc)] = (ar, ac)
    pairs = 0
    for (dr, dc), _ in sides.items():
        if (-dr, -dc) in sides:
            pairs += 1
    return pairs // 2


def capturable_adjacent(board):
    """Adjacent attackers the defender could capture with its next move."""
    king = king_square(board)
    if king is None:
        return 0
    r, c = king
    adjacent = {(r + dr, c + dc) for dr, dc in DIRECTIONS
                if 0 <= r + dr < 9 and 0 <= c + dc < 9 and board[r + dr][c + dc] == "A"}
    if not adjacent:
        return 0
    best = 0
    for move in get_legal_moves(board, "D"):
        child = apply_move(board, move, "D")
        lost = sum(1 for (ar, ac) in adjacent if child[ar][ac] != "A")
        best = max(best, lost)
    return best


def classify(board):
    escape = immediate_escape(board)
    reach = escape_reachability(board, 2)
    adjacent = adjacent_attackers(board)
    pairs = opposite_pairs(board)
    unstable = capturable_adjacent(board)
    if escape or reach:
        return "gap"
    if adjacent < 2 or pairs < 1:
        return "no_structure"
    if unstable:
        return "unstable"
    return "effective"


def king_distance(king, square):
    if king is None or square is None:
        return None
    return max(abs(king[0] - square[0]), abs(king[1] - square[1]))


def board_sequence(game):
    board = tuple(map(tuple, game["initial_board"]))
    yield 0, "A", board
    side = "A"
    for index, move in enumerate(game.get("moves") or [], start=1):
        if "board_after" in move:
            board = tuple(map(tuple, move["board_after"]))
        else:
            board = apply_move(board, (tuple(move["from_square"]), tuple(move["to_square"])), side)
        side = "D" if side == "A" else "A"
        yield index, side, board


def first_escape_ply(states):
    for ply, side, board in states:
        if side != "A":
            continue
        if immediate_escape(board) > 0:
            return ply
    return None


def analyse(game, stride=4):
    states = list(board_sequence(game))
    first_escape = first_escape_ply(states)
    labels = []
    approach_events = []
    structure = []
    king_won = game.get("winner") == "A"
    for index, (ply, side, board) in enumerate(states):
        if side != "A":
            continue
        if ply % stride:
            continue
        labels.append((ply, classify(board)))
        king = king_square(board)
        structure.append(dict(ply=ply, adjacent=adjacent_attackers(board),
                              opposite=opposite_pairs(board), captured=king_won))
        # H1: compare "closing in" moves with every other attacker move.
        if index + 1 < len(states) and index >= 1:
            move = game["moves"][ply]
            start, end = tuple(move["from_square"]), tuple(move["to_square"])
            before = king_distance(king_square(board), start)
            after = king_distance(king, end)
            if before is not None and after is not None:
                later = first_escape_ply(states[ply:])
                approach_events.append(dict(ply=ply, before=before, after=after,
                                            approach=(before >= 3 and after <= 2),
                                            escape_within=(later is not None and later <= ply + 6)))
    return dict(game_id=game.get("game_id"), winner=game.get("winner"), match=game.get("match"),
                plies=len(states), first_escape=first_escape, labels=labels,
                approaches=approach_events, structure=structure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stride", type=int, default=4)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Refusing to overwrite an existing analysis file")
    games = [json.loads(line) for line in args.corpus.open(encoding="utf-8") if line.strip()]
    records = [analyse(game, args.stride) for game in games]

    by_outcome = defaultdict(Counter)
    for record in records:
        for _, label in record["labels"]:
            by_outcome[record["winner"]][label] += 1
    print("== blockade class distribution (share of sampled attacker decisions) ==")
    for outcome in ("A", "DRAW", "D"):
        counts = by_outcome.get(outcome)
        if not counts:
            continue
        total = sum(counts.values())
        share = {k: round(v / total, 3) for k, v in counts.most_common()}
        print(f"  winner {outcome:<4} n={total:>4}  {share}")

    moves = [event for record in records for event in record["approaches"]]
    for flag, label in ((True, "closing from >=3 to <=2"), (False, "all other attacker moves")):
        subset = [event for event in moves if event["approach"] is flag]
        if not subset:
            continue
        rate = sum(1 for event in subset if event["escape_within"]) / len(subset)
        print(f"\n== H1: {label} ==")
        print(f"  events={len(subset)} escape within 6 plies={rate:.3f}")

    grouped = defaultdict(list)
    for record in records:
        for row in record["structure"]:
            grouped[(row["adjacent"], row["opposite"])].append(row["captured"])
    print("\n== H2: capture rate by (adjacent attackers, opposite pairs) ==")
    for key in sorted(grouped):
        values = grouped[key]
        if len(values) < 5:
            continue
        print(f"  adjacent={key[0]} opposite={key[1]}: n={len(values):>4} king captured={sum(values)/len(values):.3f}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(corpus=str(args.corpus), records=records), indent=2), encoding="utf-8")
    print("\nanalysis ->", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
