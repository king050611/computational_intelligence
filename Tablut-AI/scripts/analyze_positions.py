"""Extract auditable tactical examples only from validated full replays."""
import csv
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import inf
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.experimental import SearchOptions
from scripts.analyze_history import write_jsonl
from src.enhanced_search import EnhancedSearch, SearchTimeout, choose_enhanced
from src.evaluation import load_evaluator
from src.features import extract_features
from src.game import apply_move, check_winner, get_legal_moves, get_state_key, parse_board
from src.tactics import opponent

OUT = ROOT/"reports/historical_analysis"
MODEL = OUT/"v4_champion_schema2.json"


def winning_moves(board, side, history):
    other = opponent(side)
    ancestors = history + (get_state_key(board,side),)
    return [move for move in get_legal_moves(board, side)
            if check_winner(apply_move(board, move, side), other, ancestors) == side]


def partition(replays):
    groups = defaultdict(list)
    for game in replays:
        groups[game["winner"]].append(game)
    for games in groups.values():
        games.sort(key=lambda g: sha256(g["game_id"].encode()).hexdigest())
        for index, game in enumerate(games):
            yield ("holdout" if index%5==0 else "regression" if index%5==1 else "development"), game


def analyze_game(game, evaluator):
    snapshots = []
    history = ()
    for event in game["moves"]:
        side = event["player"]
        board = parse_board(event["board_before"])
        move = tuple(map(tuple,event["move"]))
        after = apply_move(board,move,side)
        ancestors = history+(get_state_key(board,side),)
        result = check_winner(after,opponent(side),ancestors)
        record = dict(game_id=game["game_id"], source=game["experiment"], version=game["version"],
                      ply=event["ply"], side=side, board=board, history=history, move=move,
                      original_score=(event.get("search") or {}).get("score"),
                      original_depth=(event.get("search") or {}).get("completed_depth"),
                      original_seconds=event.get("elapsed_seconds"), winner=game["winner"],
                      immediate_result=result, ref_static=evaluator(board,side), categories=[], alternatives=[])
        if game["winner"]!=side:
            alternatives = winning_moves(board,side,history)
            if alternatives and move not in alternatives:
                record["categories"].append("missed_immediate_win")
                record["alternatives"] = alternatives
        if result in ("A","D") and result==side:
            record["categories"].append(game["termination"] or "terminal_win")
            record["features_before_win"] = extract_features(board)
        if result=="DRAW":
            if game["termination"]=="repetition":
                record["categories"].append("active_repeat" if side==game["our_side"] else
                                            "passive_repeat" if game["our_side"] in ("A","D") else "repeat_actor_unknown")
            score=record["ref_static"] * (-1 if game["our_side"] in ("A","D") and side!=game["our_side"] else 1)
            record["position_class"] = "advantage_proxy" if score>=25 else "disadvantage_proxy" if score<=-25 else "balanced_proxy"
            safe = []
            for alternative in get_legal_moves(board,side):
                if alternative == move:
                    continue
                child = apply_move(board,alternative,side)
                terminal = check_winner(child,opponent(side),ancestors)
                if terminal == side or terminal is None and not winning_moves(child,opponent(side),ancestors):
                    safe.append(alternative)
            record["alternatives"] = list(dict.fromkeys(record["alternatives"]+safe))
            record["alternative_evidence"] = "Non-draw continuations with no immediate opponent win. Later safety is unknown."
        snapshots.append(record)
        history=ancestors
    if game["winner"] in ("A","D"):
        lost=next((x for x in reversed(snapshots) if x["side"]!=game["winner"]),None)
        if lost:
            side=lost["side"];board=lost["board"];move=lost["move"]
            other=opponent(side);ancestors=lost["history"]+(get_state_key(board,side),)
            after=apply_move(board,move,side)
            danger=winning_moves(after,other,ancestors) if check_winner(after,other,ancestors) is None else []
            safe=[]
            if danger:
                for alternative in get_legal_moves(board,side):
                    child=apply_move(board,alternative,side)
                    terminal=check_winner(child,other,ancestors)
                    if terminal in (side,"DRAW") or terminal is None and not winning_moves(child,other,ancestors):
                        safe.append(alternative)
            lost["categories"].append("avoidable_mate_in_one" if safe else "last_losing_decision")
            lost["alternatives"] = list(dict.fromkeys(lost["alternatives"]+safe))
            lost["opponent_immediate_wins"] = danger
            lost["phase"] = "opening" if lost["ply"]<20 else "middlegame" if lost["ply"]<60 else "late"
        # First known mistake may be earlier than the final tactical error.
        first=next((x for x in snapshots if x["side"]!=game["winner"] and
                    any(c in x["categories"] for c in ("missed_immediate_win","avoidable_mate_in_one"))),None)
        if first:
            first["categories"].append("first_proven_error_in_checks")
    return [s for s in snapshots if s["categories"] or "position_class" in s]


def reference(record,evaluator):
    board,side,history=record["board"],record["side"],record["history"]
    options=SearchOptions(max_depth=5,node_budget=40000)
    stats={}
    move=choose_enhanced(board,side,deadline=perf_counter()+1.5,history=history,evaluator=evaluator,
                         stats=stats,options=options)
    reference_result=dict(move=move, score=stats["score"], completed_depth=stats["completed_depth"],
                          finish_reason=stats["finish_reason"], node_cap=40000, seconds_cap=1.5)
    depth=stats["completed_depth"]
    if move!=record["move"] and depth:
        ancestors=history+(get_state_key(board,side),)
        engine=EnhancedSearch(side,perf_counter()+.5,evaluator,options,dict(nodes=0,cutoffs=0,tt_hint_hits=0))
        try:
            original,_=engine.visit(apply_move(board,record["move"],side),opponent(side),depth-1,
                                    -inf,inf,ancestors,1)
            reference_result["played_move_score_at_same_depth"]=original
        except SearchTimeout:
            reference_result["played_move_score_at_same_depth"]=None
    return reference_result


def main():
    games=[json.loads(line) for line in (OUT/"historical_games.jsonl").read_text(encoding="utf-8").splitlines()]
    full=[g for g in games if g["quality"]=="complete"]
    evaluator=load_evaluator(MODEL)
    buckets=defaultdict(list); seen={}
    all_cases=[]
    for split,game in partition(full):
        for case in analyze_game(game,evaluator):
            all_cases.append(case)
            key=(case["board"],case["side"])
            if key in seen and seen[key]!=split:
                continue
            seen[key]=split
            buckets[split].append(case)
    counts={}
    for split in ("development","regression","holdout"):
        cases=buckets[split]
        for case in cases:
            case["reference"]=reference(case,evaluator)
        counts[split]=dict(positions=len(cases), games=len({c["game_id"] for c in cases}), references=len(cases))
        write_jsonl(ROOT/f"data/positions/{split}_positions.jsonl",cases)
    categories=Counter(c for case in all_cases for c in case["categories"])
    with (OUT/"root_cause_statistics.csv").open("w",newline="",encoding="utf-8-sig") as file:
        writer=csv.writer(file)
        writer.writerow(("version","category","case_count"))
        by_version=Counter((case["version"],category) for case in all_cases for category in case["categories"])
        writer.writerows((v,c,n) for (v,c),n in sorted(by_version.items()))
        non_replay_losses=sum(g["quality"]=="summary_only" and g["our_side"] in ("A","D")
                              and g["winner"] not in (g["our_side"],"DRAW") for g in games)
        writer.writerow(("all","unknown_loss_without_replay",non_replay_losses))
    patterns={}
    for end in ("king_captured","king_escaped"):
        found=[c for c in all_cases if end in c["categories"]]
        if found:
            patterns[end]=dict(n=len(found),mean_features=[sum(c["features_before_win"][i] for c in found)/len(found)
                                                           for i in range(8)],
                               completed_depth=[c["original_depth"] for c in found if c["original_depth"] is not None])
    info=dict(splits=counts,categories=categories,winning_patterns=patterns,
              drawn_positions=Counter(c["position_class"] for c in all_cases if "position_class" in c),
              unknown_summary_losses=non_replay_losses,full_replay_wdl=Counter(g["winner"] for g in full))
    (OUT/"position_metrics.json").write_text(json.dumps(info,indent=2),encoding="utf-8")
    print(info)


if __name__=="__main__":
    main()
