"""Small NumPy policy–value network. All values use the defender's perspective."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np

from config.settings import BOARD_SIZE, DIRECTIONS


CELLS = BOARD_SIZE ** 2
ACTION_SIZE = CELLS * len(DIRECTIONS) * (BOARD_SIZE - 1)
INPUT_SIZE = 4 * CELLS + 1
HIDDEN_SIZE = 24
PIECES = np.frombuffer(b"ADKX", dtype=np.uint8)
WEIGHT_SHAPES = {
    "input_weights": (INPUT_SIZE, HIDDEN_SIZE), "hidden_bias": (HIDDEN_SIZE,),
    "value_weights": (HIDDEN_SIZE,), "value_bias": (1,),
    "policy_weights": (HIDDEN_SIZE, ACTION_SIZE), "policy_bias": (ACTION_SIZE,),
}
OUTCOME_VALUE = {"A": -1.0, "D": 1.0, "DRAW": 0.0}


def encode_board(board, side):
    cells = np.frombuffer("".join("".join(row) for row in board).encode("ascii"), dtype=np.uint8)
    features = np.empty(INPUT_SIZE, dtype=np.float32)
    features[:-1] = (PIECES[:, None] == cells).reshape(-1)
    features[-1] = 1.0 if side == "D" else -1.0
    return features


def action_id(move):
    (r, c), (nr, nc) = move
    dy, dx = nr - r, nc - c
    length = abs(dy) + abs(dx)
    direction = DIRECTIONS.index((dy // length, dx // length))
    return ((r * BOARD_SIZE + c) * len(DIRECTIONS) + direction) * (BOARD_SIZE - 1) + length - 1


def softmax(logits):
    weights = np.exp(logits - logits.max())
    return weights / weights.sum()


@dataclass
class Sample:
    board: tuple
    side: str
    result: float
    policy: tuple = ()


class Network:
    def __init__(self, weights):
        self.weights = {name: np.asarray(weights[name], dtype=np.float32)
                        for name in WEIGHT_SHAPES}
        for name, shape in WEIGHT_SHAPES.items():
            if self.weights[name].shape != shape or not np.isfinite(self.weights[name]).all():
                raise ValueError(f"Invalid network weights for {name}")

    @classmethod
    def initialize(cls, seed):
        rng = np.random.default_rng(seed)
        weights = {name: np.zeros(shape, dtype=np.float32) for name, shape in WEIGHT_SHAPES.items()}
        weights["input_weights"] = rng.normal(0, 1 / np.sqrt(INPUT_SIZE), WEIGHT_SHAPES["input_weights"])
        return cls(weights)

    def _hidden(self, features):
        return np.tanh(features @ self.weights["input_weights"] + self.weights["hidden_bias"])

    def value(self, board, side):
        hidden = self._hidden(encode_board(board, side))
        return float(np.tanh(hidden @ self.weights["value_weights"] + self.weights["value_bias"][0]))

    def predict(self, board, side, actions):
        hidden = self._hidden(encode_board(board, side))
        value = np.tanh(hidden @ self.weights["value_weights"] + self.weights["value_bias"][0])
        logits = hidden @ self.weights["policy_weights"][:, actions] + self.weights["policy_bias"][actions]
        return float(value), softmax(logits)

    def fit(self, samples, *, epochs, rng, learn_policy=False, learning_rate=0.06):
        """Fit terminal values and, when present, search visits over legal moves."""
        if not samples or epochs < 1:
            raise ValueError("Training requires samples and at least one epoch")
        features = np.stack([encode_board(sample.board, sample.side) for sample in samples])
        targets = np.asarray([sample.result for sample in samples], dtype=np.float32)
        policy_rows = []
        if learn_policy:
            for sample in samples:
                actions, probabilities = zip(*sample.policy)
                policy_rows.append((np.asarray(actions), np.asarray(probabilities, dtype=np.float32)))
        for _ in range(epochs):
            order = rng.permutation(len(samples))
            value_loss = policy_loss = 0.0
            for offset in range(0, len(order), 32):
                indexes = order[offset:offset + 32]
                x, target = features[indexes], targets[indexes]
                hidden = self._hidden(x)
                w = self.weights
                v = np.tanh(hidden @ w["value_weights"] + w["value_bias"])
                residual = v - target
                value_loss += float(residual @ residual)
                dv = (2 / len(indexes)) * residual * (1 - v * v)
                dh = dv[:, None] * w["value_weights"]
                grads = {"value_weights": hidden.T @ dv,
                         "value_bias": np.asarray([dv.sum()])}
                if learn_policy:
                    dp = np.zeros((len(indexes), ACTION_SIZE), dtype=np.float32)
                    for row, index in enumerate(indexes):
                        actions, desired = policy_rows[index]
                        predicted = softmax(hidden[row] @ w["policy_weights"][:, actions] + w["policy_bias"][actions])
                        dp[row, actions] = (predicted - desired) / len(indexes)
                        policy_loss -= float(desired @ np.log(np.maximum(predicted, 1e-8)))
                    dh += dp @ w["policy_weights"].T
                    grads["policy_weights"] = hidden.T @ dp
                    grads["policy_bias"] = dp.sum(axis=0)
                dh *= 1 - hidden * hidden
                grads["input_weights"] = x.T @ dh
                grads["hidden_bias"] = dh.sum(axis=0)
                for name, gradient in grads.items():
                    w[name] -= learning_rate * gradient
        return {"value_mse": value_loss / len(samples),
                "policy_cross_entropy": policy_loss / len(samples) if learn_policy else None}


def save_network(path, network, metadata):
    """Atomically publish one checkpoint with weights and its evaluation."""
    path = Path(path)
    file = NamedTemporaryFile(mode="wb", dir=path.parent, delete=False)
    temporary = Path(file.name)
    try:
        with file:
            np.savez_compressed(file, metadata=json.dumps(metadata, allow_nan=False), **network.weights)
        os.link(temporary, path)
    finally:
        temporary.unlink()


def load_network(path):
    with np.load(path, allow_pickle=False) as checkpoint:
        metadata = json.loads(str(checkpoint["metadata"].item()))
        if not isinstance(metadata, dict) or metadata.get("schema_version") != 1 or metadata.get("phase") not in ("value", "policy"):
            raise ValueError("Unsupported neural checkpoint")
        return Network(checkpoint), metadata
