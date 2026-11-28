from math import inf
from pathlib import Path
import unittest

from config.experimental import SearchOptions
from scripts.build_strategy_dataset import read_rows, symmetry
from src.enhanced_search import choose_enhanced
from src.game import apply_move, check_winner, get_state_key, initial_board
from src.tactics import opponent


class Phase3TacticsTests(unittest.TestCase):
    def test_exported_positions_are_reachable_and_disjoint(self):
        root=Path("data/positions")
        cases=read_rows(root/"phase3/tactical_positions.jsonl")
        reserved={symmetry(r["board"],r["side"]) for p in root.rglob("*holdout*_positions.jsonl") for r in read_rows(p)}
        seen=set()
        for case in cases:
            with self.subTest(category=case["category"],game=case["synthetic_playout"]):
                board,side,history=initial_board(),"A",[]
                for move in case["path_from_start"]:
                    history.append(get_state_key(board,side))
                    board=apply_move(board,tuple(map(tuple,move)),side)
                    side=opponent(side)
                    self.assertIsNone(check_winner(board,side,history))
                self.assertEqual(case["board"],[list(row) for row in board])
                self.assertEqual(case["side"],side)
                key=symmetry(board,side)
                self.assertNotIn(key,seen|reserved)
                seen.add(key)

    def test_search_converts_historical_immediate_wins(self):
        root=Path("data/positions/phase2")
        checked=0
        for split in ("development","regression"):
            for case in read_rows(root/f"{split}_positions.jsonl"):
                if not ({"king_captured","king_escaped"} & set(case["categories"])):
                    continue
                board=tuple(map(tuple,case["board"]))
                side=case["side"]
                history=tuple(get_state_key(b,s) for b,s in case["history"])
                move=choose_enhanced(board,side,deadline=inf,history=history,options=SearchOptions(1))
                self.assertEqual(check_winner(apply_move(board,move,side),opponent(side),
                                              history+(get_state_key(board,side),)),side)
                checked+=1
        self.assertGreater(checked,0)


    def test_historical_safe_alternatives_are_found_by_depth_two(self):
        from scripts.analyze_positions import winning_moves
        checked=0
        for split in ("development","regression"):
            for case in read_rows(Path(f"data/positions/phase2/{split}_positions.jsonl")):
                if "avoidable_mate_in_one" not in case["categories"]:
                    continue
                board=tuple(map(tuple,case["board"]))
                side=case["side"]
                history=tuple(get_state_key(b,s) for b,s in case["history"])
                move=choose_enhanced(board,side,deadline=inf,history=history,options=SearchOptions(2))
                child=apply_move(board,move,side)
                path=history+(get_state_key(board,side),)
                result=check_winner(child,opponent(side),path)
                self.assertNotEqual(result,opponent(side))
                if result is None:
                    self.assertFalse(winning_moves(child,opponent(side),path))
                checked+=1
        self.assertGreater(checked,0)
