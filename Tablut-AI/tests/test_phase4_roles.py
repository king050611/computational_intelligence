import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config.evolution import BASE_WEIGHTS
from scripts.train_role import ROOT, allocate, main, rank, summarize
from src.evaluation import FEATURE_NAMES, for_root, load_evaluator
from src.experimental_player import ExperimentalPlayer
from src.game import initial_board, get_legal_moves


class RoleTests(unittest.TestCase):
    def test_schema3_validates_features_and_fixes_root_evaluator(self):
        data=dict(schema_version=3,model_type="dual_role_evolutionary_dynamic",features=list(FEATURE_NAMES),
                  attacker_weights=[1]*8,defender_weights=[2]*8)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"dual.json"
            path.write_text(json.dumps(data))
            model=load_evaluator(path)
            bot=ExperimentalPlayer("evolutionary_dynamic",evaluator=model)
            for role in ("A","D"):
                board=initial_board()
                with patch("src.experimental_player.choose_enhanced",return_value=get_legal_moves(board,role)[0]) as search:
                    bot._play(board,role)
                    self.assertIs(search.call_args.kwargs["evaluator"],for_root(model,role))
            for corrupt in (dict(attacker_weights=[0]*7),dict(defender_weights=[True]*8),
                            dict(features=list(reversed(FEATURE_NAMES)))):
                path.write_text(json.dumps(dict(data,**corrupt)))
                with self.assertRaises(ValueError):
                    load_evaluator(path)

    def test_quota_fitness_and_win_first_sorting(self):
        self.assertEqual(Counter(allocate([dict(share=s) for s in (30,30,25,15)],12)),{0:4,1:3,2:3,3:2})
        a=summarize([dict(our_side="A",result={"winner":w}) for w in ("A","D")],"A")
        b=summarize([dict(our_side="A",result={"winner":"DRAW"})]*2,"A")
        self.assertEqual(a["points"],b["points"])
        self.assertGreater(rank(a,"win-first"),rank(b,"win-first"))
        with self.assertRaises(ValueError):
            summarize([dict(our_side="D")],"A")

    def test_each_role_runs_one_generation_and_retains_incumbent_at_floor(self):
        for role,side in (("attacker","A"),("defender","D")):
            calls=[]
            def mock_suite(out,weights,actual_side,entries,depth,pool,seed,candidate_engine=None):
                calls.append((actual_side,len(entries)))
                # Challenger wins more but scores below the incumbent's official points.
                first=out.name.endswith("_00")
                return dict(weights=weights,points=4 if first else 3,wins=0 if first else 1,reward=4)
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                pool=folder/"pool.json"
                pool.write_text(json.dumps([dict(name="control",side="D" if side=="A" else "A",
                                     share=1,engine=str(ROOT))]))
                out=folder/"run"
                args=["--output-dir",str(out),"--opponent-pool",str(pool)]
                with patch("scripts.train_role.suite",side_effect=mock_suite):
                    main(role,args)
                    main(role,args+["--resume"])
                self.assertEqual(calls,([(side,4)]*8+[(side,12)]*4)*2)
                expected=load_evaluator(ROOT/"models/attacker/best.json").weights
                self.assertEqual(load_evaluator(out/f"{role}_best.json").weights,expected)
                ck=json.loads((out/"checkpoint-0002.json").read_bytes())
                self.assertEqual(len({tuple(w) for w in ck["population"]}),8)


from collections import Counter
