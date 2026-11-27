import contextlib
import io
import json
from pathlib import Path
import unittest

from scripts.import_external_games import classify, decode
from scripts.build_strategy_dataset import symmetry
from src.game import initial_board


class ExternalImportTests(unittest.TestCase):
    def test_coordinate_convention(self):
        self.assertEqual(decode("D1-C1"), ((0,3),(0,2)))
        with self.assertRaises(ValueError):
            decode("a0-a1")

    def test_mirrored_opening_has_same_key(self):
        board=initial_board()
        moved=[list(row) for row in board]
        moved[0][3],moved[0][2]=moved[0][2],moved[0][3]
        self.assertEqual(symmetry(moved,"D"),symmetry([row[::-1] for row in moved],"D"))
        self.assertNotEqual(symmetry(moved,"D"),symmetry(moved,"A"))

    def test_replay_checks_captures_and_terminal_labels(self):
        source=Path("reports/replays/depth_greedy/games.json")
        game=json.loads(source.read_bytes())["games"][0]
        game={**game,"game_id":"test","moves":[{**m,"captures":[[*c["square"],c["piece"]] for c in m["captures"]]} for m in game["moves"]]}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(classify(game,{"course_rules_equivalent":True})["classification"],"A")
            other=classify(game,{"course_rules_equivalent":False})
            self.assertEqual(other["classification"],"B")
            self.assertIsNone(other["course_result"])
            game["moves"][1]["captures"]=[[0,0,"A"]]
            damaged=classify(game,{"course_rules_equivalent":True})
            self.assertEqual(damaged["classification"],"B")
            self.assertEqual(len(damaged["moves"]),1)


    def test_missing_source_snapshots_cannot_reach_exact_set(self):
        game=json.loads(Path("reports/replays/depth_greedy/games.json").read_bytes())["games"][0]
        moves=[dict(player=m["player"],move=m["move"]) for m in game["moves"]]
        with contextlib.redirect_stdout(io.StringIO()):
            result=classify(dict(game,moves=moves),{"course_rules_equivalent":True})
        self.assertEqual(result["classification"],"B")
        self.assertEqual(result["moves"],[])
        self.assertEqual(result["first_unverified_ply"],1)
        self.assertIsNone(result["course_result"])
