"""V7 deployment pin: attacker = frozen V5 engine + champion weights, defenders frozen.

The record must stay byte-consistent with the files it names; if any engine, model or
pool file changes, this test fails and the pin has to be re-issued deliberately.
"""
import hashlib
import json
import unittest
from pathlib import Path

from scripts.train_role import fingerprint, model_spec

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "reports/phase4/ROLE_CONFIG_v7.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


class RoleConfigPinTests(unittest.TestCase):
    def test_candidate_engine_matches_the_pin(self):
        candidate = load()["candidate"]
        engine = ROOT / candidate["engine"]
        self.assertTrue(engine.is_dir())
        self.assertEqual(fingerprint(engine), candidate["engine_files"])

    def test_candidate_model_matches_the_pin(self):
        candidate = load()["candidate"]
        self.assertEqual(sha256(ROOT / candidate["model"]), candidate["model_sha256"])

    def test_defender_pool_matches_the_pin(self):
        config = load()
        pool_path = ROOT / config["opponent_pool"]["path"]
        self.assertEqual(sha256(pool_path), config["opponent_pool"]["sha256"])
        entries = json.loads(pool_path.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), config["opponent_pool"]["entries"])
        for entry in entries:
            engine = (pool_path.parent / entry["engine"]).resolve()
            model = pool_path.parent / entry["model"]
            self.assertEqual(fingerprint(engine), entry["files"], entry["name"])
            self.assertEqual(sha256(model), entry["model_sha256"], entry["name"])

    def test_pinned_pool_is_accepted_by_the_trainer(self):
        config = load()
        pool_path = ROOT / config["opponent_pool"]["path"]
        for entry in json.loads(pool_path.read_text(encoding="utf-8")):
            engine = (pool_path.parent / entry["engine"]).resolve()
            model = pool_path.parent / entry["model"]
            spec = model_spec(engine, model, entry["depth"], entry["seconds"])
            self.assertEqual(spec["files"], entry["files"])
            self.assertEqual(spec["model_sha256"], entry["model_sha256"])
        candidate = config["candidate"]
        spec = model_spec(ROOT / candidate["engine"], ROOT / candidate["model"],
                          candidate["depth"], candidate["seconds"])
        self.assertEqual(spec["files"], candidate["engine_files"])
        self.assertEqual(spec["model_sha256"], candidate["model_sha256"])

    def test_the_pin_states_its_own_caveat(self):
        config = load()
        self.assertEqual(config["role"], "attacker")
        self.assertEqual(config["search"]["depth"], 4)
        self.assertEqual(config["search"]["seconds"], 60)
        self.assertIn("not a promoted model", config["evidence"]["caveat"])


if __name__ == "__main__":
    unittest.main()
