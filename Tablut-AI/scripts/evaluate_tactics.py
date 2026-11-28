"""Run reproducible, node-capped tactical diagnostics on a preassigned split."""
import argparse
from collections import Counter
import json
from pathlib import Path
from time import perf_counter

from config.experimental import SearchOptions
from scripts.build_strategy_dataset import read_rows
from src.enhanced_search import choose_enhanced
from src.evaluation import for_root, load_evaluator
from src.game import get_state_key, is_legal_move


def evaluate_cases(cases,evaluator,depth=4,nodes=2000):
    stats_by_type={}
    for case in cases:
        board=tuple(map(tuple,case["board"]))
        side=case["side"]
        history=tuple(get_state_key(b,s) for b,s in case["history"])
        stats={}
        start=perf_counter()
        move=choose_enhanced(board,side,deadline=start+5,history=history,
                evaluator=for_root(evaluator,side),options=SearchOptions(depth,node_budget=nodes),stats=stats)
        answers={tuple(map(tuple,m)) for m in case["answers"]}
        row=stats_by_type.setdefault(case["category"],Counter(games=0,listed_choice=0,illegal=0,seconds=0))
        row.update(games=1,listed_choice=int(move in answers),illegal=int(not is_legal_move(board,move,side)),
                   seconds=perf_counter()-start)
    return stats_by_type


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases",type=Path,required=True)
    parser.add_argument("--model",type=Path,action="append",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--nodes",type=int,default=2000)
    args=parser.parse_args()
    if args.nodes<1:
        parser.error("Positive node budget required")
    cases=read_rows(args.cases)
    report={p.name:evaluate_cases(cases,load_evaluator(p),nodes=args.nodes) for p in args.model}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as file:
        json.dump(dict(cases=str(args.cases),depth=4,nodes=args.nodes,models=report),file,indent=2)


if __name__=="__main__":
    main()
