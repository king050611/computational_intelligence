"""Validate locally supplied, authorized external Tablut JSON and route A/B/C records."""
import argparse
import contextlib
import io
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from scripts.replay_demo import Tablut
from scripts.analyze_history import write_jsonl
from src.game import apply_move, check_winner, get_state_key, initial_board, is_legal_move, parse_board


def decode(value):
    if isinstance(value,str):
        match=re.fullmatch(r"([a-i])([1-9])-([a-i])([1-9])",value.lower())
        if not match:
            raise ValueError("invalid move notation")
        a,r,b,s=match.groups()
        return ((int(r)-1,ord(a)-97),(int(s)-1,ord(b)-97))
    return tuple(tuple(square) for square in value)


def classify(game, meta):
    prefix=[]
    evidence_gap=False
    reason=None
    history=[]
    side="A"
    end=None
    try:
        board=parse_board(game["initial_board"])
        if board!=initial_board():
            raise ValueError("initial board differs from course setup")
        referee=Tablut()
        referee.past_positions=[referee.compute_zobrist_hash(True)]
        if not isinstance(game["moves"],list) or not game["moves"]:
            raise ValueError("missing move record")
        for ply,event in enumerate(game["moves"],1):
            if end is not None:
                raise ValueError("play continues after course terminal position")
            if event["player"]!=side:
                raise ValueError("wrong side to move")
            move=decode(event["move"])
            if not is_legal_move(board,move,side):
                raise ValueError("illegal course move")
            if event.get("board_before") is not None and parse_board(event["board_before"])!=board:
                raise ValueError("source board before move differs")
            child=apply_move(board,move,side)
            captures=sorted([r,c,board[r][c]] for r in range(9) for c in range(9)
                if (r,c)!=move[0] and board[r][c] in "ADK" and child[r][c] in ".X")
            if event.get("board_after") is not None and normalize_board(event["board_after"])!=child:
                raise ValueError("source board after move differs")
            if event.get("captures") is not None and sorted(event["captures"])!=captures:
                raise ValueError("capture list differs")
            verified=event.get("board_after") is not None and event.get("captures") is not None
            evidence_gap |= not verified
            if not referee.make_move(side=="A",move):
                raise ValueError("course referee rejected engine-legal move")
            if normalize_board(referee.board)!=child:
                raise ValueError("course referee board differs from engine")
            other="D" if side=="A" else "A"
            previous=history+[get_state_key(board,side)]
            end=check_winner(child,other,previous)
            if referee.check_if_game_over(other=="A")!=(end is not None) or (end is not None and (referee.winner or "DRAW")!=end):
                raise ValueError("course referee result differs from engine")
            prefix.append(dict(ply=ply,player=side,move=move,board_before=board,board_after=child,
                               captures=captures,source_transition_verified=verified))
            history=previous
            side,board=other,child
        actual_reason=(("king_captured" if end=="A" else
                        "king_escaped" if any(board[r][c]=="K" for r in range(9) for c in range(9)
                                              if r in (0,8) or c in (0,8)) else "fewer_than_two_attackers") if end in ("A","D")
                       else ("repetition" if get_state_key(board,side) in history else "no_legal_moves") if end=="DRAW" else None)
        if end is None or (end,actual_reason)!=(game["result"]["winner"],game["result"]["reason"]):
            raise ValueError("terminal result or reason differs")
        if evidence_gap:
            reason="source board or capture evidence absent"
        elif meta.get("course_rules_equivalent") is not True:
            reason="rule variant equivalence not established"
    except (ValueError,TypeError,KeyError,IndexError) as exc:
        reason=str(exc)
    # A rules-engine disagreement invalidates the sample rather than accepting its prefix.
    hard_fault=reason and ("referee" in reason or reason in ("wrong side to move","invalid move notation"))
    classification="A" if reason is None else "B" if prefix and not hard_fault else "C"
    return dict(game_id=game.get("game_id"),classification=classification,reason=reason,
                first_unverified_ply=next((m["ply"] for m in prefix if not m["source_transition_verified"]),
                                          len(prefix)+1 if reason else None),
                source=meta, initial_board=game.get("initial_board"), moves=prefix if classification=="A" else verified_prefix(prefix) if classification=="B" else [],
                course_result=game.get("result") if classification=="A" else None)


def normalize_board(value):
    board=[list(row) for row in value]
    if len(board)==9 and all(len(row)==9 for row in board) and board[4][4]=="." and not any("K" in row for row in board):
        board[4][4]="X"
    return parse_board(board)


def verified_prefix(moves):
    result=[]
    for event in moves:
        if not event["source_transition_verified"]:
            break
        result.append(event)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    raw=args.input.read_bytes()
    bundle=json.loads(raw)
    meta=bundle["source"]
    required=("url","variant","year","rules_url","permission_evidence")
    if meta.get("research_use_authorized") is not True or any(not meta.get(key) for key in required):
        parser.error("Provide documented research-use permission and provenance before import")
    meta=dict(meta,raw_sha256=sha256(raw).hexdigest())
    ids=[game["game_id"] for game in bundle["games"]]
    if len(ids)!=len(set(ids)):
        parser.error("Duplicate source game IDs")
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/"raw").mkdir()
    (args.output/"raw"/"bundle.json").write_bytes(raw)
    rows=[]
    seen=set()
    for game in bundle["games"]:
        with contextlib.redirect_stdout(io.StringIO()):
            row=classify(game,meta)
        if row["classification"]=="A":
            fingerprint=tuple(m["move"] for m in row["moves"])
            if fingerprint in seen:
                row.update(classification="C",reason="duplicate complete game",moves=[],course_result=None)
            seen.add(fingerprint)
        rows.append(row)
    (args.output/"source_manifest.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    for kind,name in zip("ABC",("validated","strategy_reference","rejected")):
        write_jsonl(args.output/name/"games.jsonl",[row for row in rows if row["classification"]==kind])
    print(Counter(row["classification"] for row in rows))


if __name__=="__main__":
    main()
