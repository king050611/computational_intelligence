"""Mine reproducible tactical cases from legal, synthetic playouts."""
from collections import Counter
import json
from math import inf
from pathlib import Path
from random import Random

from scripts.analyze_history import write_jsonl
from scripts.build_strategy_dataset import symmetry, read_rows
from src.game import apply_move, check_winner, get_legal_moves, get_state_key, initial_board
from src.features import extract_features, immediate_king_threat
from src.tactics import opponent, analyze
from src.evaluation import load_evaluator


def repeat_case(board,side,history,played,rng,evaluator):
    """Build a legal four-ply shuffle without ending the game before its last move."""
    start=board
    record=list(history)
    sequence=list(played)
    turn=side
    forward=[]
    for step in range(3):
        moves=get_legal_moves(board,turn)
        if not moves:
            return
        if step==2:
            move=tuple(reversed(forward[0]))
            if move not in moves:
                return
        else:
            move=rng.choice(moves)
            forward.append(move)
        record.append(get_state_key(board,turn))
        next_board=apply_move(board,move,turn)
        turn=opponent(turn)
        if check_winner(next_board,turn,record) is not None:
            return
        board=next_board
        sequence.append(move)
    move=tuple(reversed(forward[1]))
    if move not in get_legal_moves(board,turn):
        return
    repeated=apply_move(board,move,turn)
    if repeated!=start or check_winner(repeated,opponent(turn),record+[get_state_key(board,turn)])!="DRAW":
        return
    score=evaluator(board,turn)
    if abs(score)>=25:
        return ("advantage_draw" if score>0 else "disadvantage_draw",board,turn,record,sequence,move,score)


def mate_in_two(children,history):
    for move,child in children:
        if check_winner(child,"D",history) is not None:
            continue
        replies=get_legal_moves(child,"D")
        path=history+(get_state_key(child,"D"),)
        for reply in replies:
            leaf=apply_move(child,reply,"D")
            if check_winner(leaf,"A",path) is not None:
                break
            king=next((r,c) for r in range(9) for c in range(9) if leaf[r][c]=="K")
            if not immediate_king_threat(leaf,king):
                break
        else:
            return move


def main():
    rng=Random(73123)
    evaluator=load_evaluator("reports/historical_analysis/v4_champion_schema2.json")
    path=Path("data/positions")
    reserved={symmetry(row["board"],row["side"])
              for file in path.rglob("*holdout*_positions.jsonl") for row in read_rows(file)}
    counts=Counter()
    cases=[]
    seen=set(reserved)
    for game in range(300):
        board=initial_board()
        side="A"
        history=()
        played=[]
        for _ in range(80):
            key=get_state_key(board,side)
            other=opponent(side)
            king=next((r,c) for r in range(9) for c in range(9) if board[r][c]=="K")
            features=extract_features(board)
            moves=get_legal_moves(board,side)
            children=[(move,apply_move(board,move,side)) for move in moves]
            prior=history+(key,)
            tag=None
            answers=[]
            orbit=symmetry(board,side)
            if orbit not in seen:
                if side=="A" and counts["capture_one"]<30:
                    answers=[m for m,b in children if not any("K" in row for row in b)]
                    tag="capture_one" if answers else None
                if side=="D" and features[1]>0:
                    category="two_exit_routes" if features[1]>=.5 else "escape_one"
                    if counts[category]>=30:
                        category="escape_one"
                    if counts[category]<30:
                        answers=[m for m,b in children if m[0]==king and (0 in m[1] or 8 in m[1])]
                        tag=category if answers else None
                if not tag and side=="A" and features[1]>0 and counts["blockade_one"]<30:
                    answers=[m for m,b in children if check_winner(b,other,prior) is None and not extract_features(b)[1]]
                    tag="blockade_one" if answers else None
                if not tag and side=="D" and not features[1] and counts["safe_reply"]<30 and immediate_king_threat(board,king):
                    info=analyze(board,side,inf,history)
                    answers=list(info.safe_replies)
                    tag="safe_reply" if answers else None
                if not tag and side=="D" and not features[1] and counts["create_exit"]<30:
                    answers=[m for m,b in children if check_winner(b,other,prior) is None and extract_features(b)[1]>0]
                    tag="create_exit" if answers else None
                if tag and counts[tag]<30:
                    counts[tag]+=1
                    seen.add(orbit)
                    cases.append(dict(category=tag,board=board,side=side,history=history,answers=answers,
                        path_from_start=played[:],seed=73123,synthetic_playout=game,
                        evidence="immediate observable rule condition; multi-turn advantage unproven"))
            if counts["advantage_draw"]<30 or counts["disadvantage_draw"]<30:
                repeated=repeat_case(board,side,history,played,rng,evaluator)
                if repeated:
                    name,b,t,h,line,m,score=repeated
                    k=symmetry(b,t)
                    if counts[name]<30 and k not in seen:
                        counts[name]+=1
                        seen.add(k)
                        cases.append(dict(category=name,board=b,side=t,history=h,answers=[m],
                            static_score=score,path_from_start=line,seed=73123,synthetic_playout=game,
                            evidence="repetition proved; advantage inferred from static score only"))
            if side=="A" and orbit not in seen and features[0] and counts["capture_two"]<30 and not immediate_king_threat(board,king):
                solution=mate_in_two(children,prior)
                if solution:
                    counts["capture_two"]+=1
                    seen.add(orbit)
                    cases.append(dict(category="capture_two",board=board,side=side,history=history,
                        answers=[solution],path_from_start=played[:],seed=73123,synthetic_playout=game,
                        evidence="every legal defender reply permits next-move king capture"))
            move,board=rng.choice(children)
            played.append(move)
            side=other
            history=prior
            if check_winner(board,side,history) is not None:
                break
        if all(counts[tag]>=30 for tag in ("capture_one","escape_one","two_exit_routes","blockade_one","safe_reply","create_exit","capture_two","advantage_draw","disadvantage_draw")):
            break
    write_jsonl(path/"phase3"/"tactical_positions.jsonl",cases)
    print(json.dumps(counts))


if __name__=="__main__":
    main()
