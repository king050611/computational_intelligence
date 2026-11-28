"""V7 Phase 1 (P0-2/P0-3): dissect attacker games in a recorded corpus.

Reads a JSONL corpus of finished games (each with per-move boards), replays them, and
reports the blockade/escape indicators around the moments where the attacker lost the
initiative. Analysis only: nothing here is imported by the search or the evaluator.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.blockade import snapshot
from src.game import apply_move, check_winner, get_legal_moves

EDGE = {0, 8}


def load_games(path):
    games = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                games.append(json.loads(line))
    return games


def board_sequence(game):
    """Yield (ply, side_to_move, board) starting from the recorded initial position."""
    board = tuple(map(tuple, game["initial_board"]))
    yield 0, "A", board
    side = "A"
    for index, move in enumerate(game.get("moves") or [], start=1):
        if "board_after" in move:
            board = tuple(map(tuple, move["board_after"]))
        else:
            start, end = move.get("from_square"), move.get("to_square")
            if start is None or end is None:
                break
            board = apply_move(board, (tuple(start), tuple(end)), side)
        side = "D" if side == "A" else "A"
        yield index, side, board


def played_move(game, index):
    moves = game.get("moves") or []
    if index < 1 or index > len(moves):
        return None
    move = moves[index - 1]
    start, end = move.get("from_square"), move.get("to_square")
    return (tuple(start), tuple(end)) if start is not None and end is not None else None


def analyse_game(game, stride=4, perspective="attacker"):
    """Walk one game and collect the attacker-relevant events.

    ``perspective="attacker"`` analyses every game from the attacking side's point of
    view (so a corpus of engine-vs-engine matches can be pooled). ``"our_side"`` keeps
    the older behaviour of only reading games our own candidate played as attacker.
    """
    side_of_interest = "A" if perspective == "attacker" else game.get("our_side")
    record = dict(game_id=game.get("game_id"), our_side=game.get("our_side"),
                  match=game.get("match"), perspective=perspective,
                  winner=game.get("winner"), termination=game.get("termination"),
                  plies=game.get("plies") or len(game.get("moves") or []),
                  events=[], first_immediate_escape=None, first_reach_2=None,
                  missed_mates=[], final=dict())
    for ply, side, board in board_sequence(game):
        terminal = check_winner(board, side)
        if terminal is not None:
            record["final"] = dict(ply=ply, terminal=terminal,
                                   defenders=sum(row.count("D") for row in board),
                                   attackercaptures=None)
            break
        # Only evaluate positions where the attacker is to move (our decision points).
        if side != "A" or side_of_interest != "A":
            continue
        heavy = ply % stride == 0
        if heavy:
            data = snapshot(board)
        else:
            from src.blockade import adjacent_attackers, escape_reachability, immediate_escape, king_moves
            data = dict(king_adjacent_attackers=adjacent_attackers(board),
                        king_moves=len(king_moves(board)),
                        immediate_escape=immediate_escape(board),
                        escape_reach_2=escape_reachability(board, 2))
        if data.get("immediate_escape", 0) > 0 and record["first_immediate_escape"] is None:
            record["first_immediate_escape"] = ply
        if data.get("escape_reach_2", 0) > 0 and record["first_reach_2"] is None:
            record["first_reach_2"] = ply
        if heavy:
            move = played_move(game, ply + 1)
            if data.get("attacker_mates") and move is not None:
                child = apply_move(board, move, "A")
                if check_winner(child, "D") != "A":
                    record["missed_mates"].append(dict(ply=ply, mates=data["attacker_mates"], played=move))
            record["events"].append(dict(ply=ply, **{k: v for k, v in data.items() if k != "attacker_mates"}))
    return record


def summarise(records):
    groups = {}
    for record in records:
        key = (record["perspective"], record["winner"])
        groups.setdefault(key, []).append(record)

    lines = []
    for key in sorted(groups, key=lambda k: (k[0], str(k[1]))):
        games = groups[key]
        count = len(games)
        escaped = [g["first_reach_2"] for g in games if g["first_reach_2"] is not None]
        immediate = [g["first_immediate_escape"] for g in games if g["first_immediate_escape"] is not None]
        missed = sum(len(g["missed_mates"]) for g in games)
        with_missed = sum(1 for g in games if g["missed_mates"])
        mean_plies = sum(g["plies"] for g in games) / count
        lines.append(dict(side=key[0], winner=key[1], games=count, mean_plies=round(mean_plies, 1),
                          first_reach_2_mean=round(sum(escaped) / len(escaped), 1) if escaped else None,
                          first_immediate_escape_mean=round(sum(immediate) / len(immediate), 1) if immediate else None,
                          games_with_missed_mate=with_missed, missed_mate_decisions=missed))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--perspective", choices=("attacker", "our_side"), default="attacker")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Refusing to overwrite an existing analysis file")
    games = load_games(args.corpus)
    records = [analyse_game(game, args.stride, args.perspective) for game in games]
    summary = summarise(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(corpus=str(args.corpus), games=len(games),
                                           stride=args.stride, summary=summary, records=records),
                                      indent=2), encoding="utf-8")
    for line in summary:
        print(line)
    print("analysis ->", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
