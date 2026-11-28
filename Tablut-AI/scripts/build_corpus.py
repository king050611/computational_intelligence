"""V7 Phase 2: merge and validate recorded corpora into one replayable JSONL.

Every game is replayed with the rule engine: each move must be legal and the resulting
board must equal the recorded ``board_after``. Duplicate games (same opening and same
move sequence) are dropped, and a short provenance/validation report is printed.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.game import apply_move, check_winner, get_state_key, has_any_move, is_legal_move, parse_board


def normalise(game, source):
    result = game.get("result") or {}
    return dict(game_id=game.get("game_id") or f"{source}:{game.get('game')}",
                source=source, match=game.get("match"), our_side=game.get("our_side"),
                winner=game.get("winner") or result.get("winner"),
                termination=game.get("termination") or result.get("reason"),
                initial_board=game["initial_board"], moves=game["moves"],
                strategies=game.get("strategies"))


def game_key(record):
    payload = json.dumps([record["initial_board"],
                          [[m.get("from_square"), m.get("to_square")] for m in record["moves"]]],
                         sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def validate(record):
    """Replay the game; return (ok, reason) and the number of plies checked."""
    index = 0
    try:
        board = parse_board(record["initial_board"])
        side = "A"
        history = set()
        terminal = check_winner(board, side)
        repeated = False
        for index, event in enumerate(record["moves"], start=1):
            if terminal is not None:
                return False, f"ply {index}: move after terminal result", index
            if event.get("player", side) != side or event.get("accepted", True) is not True:
                return False, f"ply {index}: wrong side or rejected move", index
            if "board_before" in event and parse_board(event["board_before"]) != board:
                return False, f"ply {index}: board_before mismatch", index
            played = (tuple(event["from_square"]), tuple(event["to_square"]))
            if not is_legal_move(board, played, side):
                return False, f"ply {index}: illegal move {played}", index
            history.add(get_state_key(board, side))
            child = apply_move(board, played, side)
            if "board_after" in event:
                after = [list(row) for row in event["board_after"]]
                if after[4][4] == "." and board[4][4] == "K" and not any("K" in row for row in child):
                    after[4][4] = "X"
                if parse_board(after) != child:
                    return False, f"ply {index}: board_after mismatch", index
            board = child
            side = "D" if side == "A" else "A"
            repeated = get_state_key(board, side) in history
            terminal = check_winner(board, side, history)
        if terminal is None or terminal != record["winner"]:
            return False, f"terminal winner mismatch: expected {terminal!r}", index
        if index == 0:
            return False, "empty game", index
        if terminal == "DRAW":
            reason = "repetition" if repeated and has_any_move(board, side) else "no_legal_moves"
        elif terminal == "A":
            reason = "king_captured"
        elif any("K" in row for row in (board[0], board[-1])) or any(row[0] == "K" or row[-1] == "K" for row in board):
            reason = "king_escaped"
        else:
            reason = "fewer_than_two_attackers"
        if record["termination"] != reason:
            return False, f"terminal reason mismatch: expected {reason}", index
        return True, "", index
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        return False, f"ply {index}: {exc}", index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, action="append", required=True,
                        help="JSONL corpus (repeatable)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.report.exists():
        parser.error("Refusing to overwrite an existing corpus or report")

    records, seen = [], set()
    stats = Counter()
    rejected = []
    for path in args.corpus:
        source = path.stem
        for line in path.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            record = normalise(json.loads(line), source)
            stats[f"{source}:input"] += 1
            ok, reason, plies = validate(record)
            if not ok:
                rejected.append(dict(game_id=record["game_id"], source=source, reason=reason))
                stats[f"{source}:invalid"] += 1
                continue
            key = game_key(record)
            if key in seen:
                stats[f"{source}:duplicate"] += 1
                continue
            seen.add(key)
            record["plies"] = plies
            records.append(record)
            stats[f"{source}:accepted"] += 1

    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    report = dict(sources=[str(path) for path in args.corpus], totals=dict(
        input=sum(v for k, v in stats.items() if k.endswith(":input")),
        accepted=len(records), rejected=len(rejected),
        duplicate=sum(v for k, v in stats.items() if k.endswith(":duplicate"))),
        by_source=dict(stats), winners=dict(Counter(r["winner"] for r in records)),
        terminations=dict(Counter(r["termination"] for r in records)),
        rejected=rejected)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["totals"], indent=2))
    print("by_source:", dict(stats))
    print("winners:", report["winners"])
    print("terminations:", report["terminations"])
    for item in rejected[:5]:
        print("  rejected:", item)
    print("corpus ->", args.output, "| report ->", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
