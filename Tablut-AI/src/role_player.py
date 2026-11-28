"""Separate process and clock state for each independent role engine."""
from hashlib import sha256
import json
from pathlib import Path

from weakref import finalize

from src.engine_process import Engine
from src.game import initial_board

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(directory):
    return {path.relative_to(directory).as_posix(): sha256(path.read_bytes()).hexdigest()
            for folder in ("src", "config") for path in sorted((directory / folder).rglob("*.py"))}


def _close_engines(engines):
    for engine in engines.values():
        engine.close()
    engines.clear()


def role_spec(side, *, verify_attacker=False):
    if side not in ("A", "D"):
        raise ValueError("Expected A or D")
    key = "attacker" if side == "A" else "defender"
    config = json.loads((ROOT / "config/roles.json").read_bytes())[key]
    engine, model = ROOT / config["engine"], ROOT / config["model"]
    if side == "D" or verify_attacker:
        if fingerprint(engine) != config["files"] or sha256(model.read_bytes()).hexdigest() != config["model_sha256"]:
            raise ValueError(f"{key} does not match the configured snapshot")
    return dict(engine=str(engine), model=str(model), depth=config["depth"],
                nodes=config["nodes"], seconds=config["seconds"])


class RolePlayer:
    def __init__(self, *, opening=None, record_search=False, verify_attacker=False):
        self.opening = initial_board() if opening is None else opening
        self.record_search = record_search
        self.verify_attacker = verify_attacker
        self.last_search_stats = None
        self._engines = {}
        self._finalizer = finalize(self, _close_engines, self._engines)

    def _play(self, side, board):
        if side not in self._engines:
            self._engines[side] = Engine(role_spec(side, verify_attacker=self.verify_attacker), self.opening)
        engine = self._engines[side]
        move = engine.play(side, board)
        self.last_search_stats = engine.last_search_stats if self.record_search else None
        return tuple(map(tuple, move)) if move is not None else None

    def play_attacker(self, board):
        return self._play("A", board)

    def play_defender(self, board):
        return self._play("D", board)

    def close(self):
        _close_engines(self._engines)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
