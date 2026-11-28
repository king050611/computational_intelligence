"""V7 Phase 2: deterministic blockade analysis over every attacker decision.

Fixes from the Phase 1 review:

* every attacker decision gets the full one-move-win check (no stride sampling);
* blockade is judged on two axes (control vs capture), never one merged label;
* the escape risk of a move is read from the **position the defender faces** (after the
  attacker's move), not from the position before it;
* capture formations are region-aware and confirmed by the rule engine.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.blockade import classify, immediate_escape, king_square
from src.game import apply_move, check_winner, get_legal_moves, get_state_key

EDGE = {0, 8}


def board_states(game):
    """Yield (ply, side_to_move, board) for a recorded game."""
    board = tuple(map(tuple, game["initial_board"]))
    yield 0, "A", board
    side = "A"
    for index, move in enumerate(game.get("moves") or [], start=1):
        board = apply_move(board, (tuple(move["from_square"]), tuple(move["to_square"])), side)
        side = "D" if side == "A" else "A"
        yield index, side, board


def king_distance(king, square):
    if king is None or square is None:
        return None
    return max(abs(king[0] - square[0]), abs(king[1] - square[1]))


def attacking_mates(board):
    """All attacker moves that capture the king (confirmed by the rule engine)."""
    mates = []
    for move in get_legal_moves(board, "A"):
        if check_winner(apply_move(board, move, "A"), "D") == "A":
            mates.append(move)
    return mates


def analyse_game(game):
    states = list(board_states(game))
    record = dict(game_id=game.get("game_id"), source=game.get("source"), match=game.get("match"),
                  winner=game.get("winner"), plies=len(states) - 1,
                  decisions=[], missed_mates=[], broke_blockade=[])
    history = set()
    for ply, side, board in states:
        history.add(get_state_key(board, side))
        if side != "A" or ply + 1 >= len(states):
            continue
        move_entry = game["moves"][ply]
        played = (tuple(move_entry["from_square"]), tuple(move_entry["to_square"]))
        child = states[ply + 1][2] if "board_after" in move_entry else apply_move(board, played, "A")
        king = king_square(board)
        before = immediate_escape(board)
        after = immediate_escape(child)
        mates = attacking_mates(board)
        missed = bool(mates) and played not in mates
        approach = None
        distance_before = king_distance(king, move_entry["from_square"])
        distance_after = king_distance(king_square(child), tuple(move_entry["to_square"]))
        if distance_before is not None and distance_after is not None:
            approach = distance_before >= 3 and distance_after <= 2
        label = classify(board, history)
        record["decisions"].append(dict(
            ply=ply, control=label["control"], capture=label["capture"],
            control_label=label["control_label"], capture_label=label["capture_label"],
            region=label["region"], immediate_escape_before=before, immediate_escape_after=after,
            geometric_escape=label["geometric_escape"], tactical_escape=label["tactical_escape"],
            self_blockade=label["self_blockade"], attacker_blockade=label["attacker_blockade"],
            controlled_corridor=label["controlled_corridor"], key_blockers=label["key_blockers"],
            unstable_blockers=label["unstable_blockers"], stable_blockade=label["stable_blockade"],
            adjacent_attackers=label["adjacent_attackers"], approach=approach,
            mates_available=len(mates), missed_mate=missed,
            formation_completion=label["formation"]["completion"],
            immediate_capture=label["formation"]["immediate_capture"]))
        if missed:
            record["missed_mates"].append(dict(ply=ply, mates=len(mates), played=played))
        if before == 0 and after > 0:
            record["broke_blockade"].append(dict(ply=ply, played=played, approach=approach))
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Refusing to overwrite an existing analysis file")
    games = [json.loads(line) for line in args.corpus.open(encoding="utf-8") if line.strip()]
    records = [analyse_game(game) for game in games]

    labels = defaultdict(Counter)
    for record in records:
        for decision in record["decisions"]:
            labels[record["winner"]][f"{decision['control_label']}/{decision['capture_label']}"] += 1
    print("== two-axis blockade labels (share of attacker decisions) ==")
    for outcome in ("A", "DRAW", "D"):
        counts = labels.get(outcome)
        if not counts:
            continue
        total = sum(counts.values())
        print(f"  winner {outcome:<4} decisions={total:>4}  "
              + "  ".join(f"{name}={counts[name] / total:.3f}" for name in sorted(counts)))

    total_decisions = sum(len(record["decisions"]) for record in records)
    missed = [m for record in records for m in record["missed_mates"]]
    print(f"\n== one-move wins over every attacker decision ==")
    print(f"  decisions checked={total_decisions}  missed mates={len(missed)}"
          + (f"  games affected={sum(1 for r in records if r['missed_mates'])}" if missed else ""))

    broke = [event for record in records for event in record["broke_blockade"]]
    approaches = [d for record in records for d in record["decisions"] if d["approach"] is not None]
    print(f"\n== H1: escape created by the move, read from the defender's position ==")
    for flag, label in ((True, "closing from >=3 to <=2"), (False, "all other attacker moves")):
        subset = [d for d in approaches if d["approach"] is flag]
        if not subset:
            continue
        opened = sum(1 for d in subset if d["immediate_escape_after"] > 0)
        broke_here = sum(1 for d in subset
                         if d["immediate_escape_before"] == 0 and d["immediate_escape_after"] > 0)
        print(f"  {label:<26} n={len(subset):>4} escape_after={opened / len(subset):.3f} "
              f"broke_blockade={broke_here / len(subset):.3f}")

    print(f"\n== blockade breaches ==")
    print(f"  decisions that opened the first escape: {len(broke)}")
    for outcome in ("A", "DRAW", "D"):
        subset = [r for r in records if r["winner"] == outcome]
        breaches = sum(len(r["broke_blockade"]) for r in subset)
        print(f"  winner {outcome:<4} games={len(subset):>2} breaches={breaches:>3} "
              f"per_game={(breaches / len(subset) if subset else 0):.2f}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(corpus=str(args.corpus), records=records), indent=2),
                           encoding="utf-8")
    print("\nanalysis ->", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
