"""A trainable leaf evaluator with the same interface as the hand-tuned scorer."""
from dataclasses import dataclass
import json
from math import fsum, isfinite
from pathlib import Path

from src.evaluation import _features


def model_features(board):
    """Scaled Tablut features and an intercept, from the defender's perspective."""
    pressure, escapes, material = _features(board)
    return pressure / 4, escapes / 4, material / 16, 1.0


@dataclass(frozen=True)
class LinearEvaluator:
    weights: tuple

    def __post_init__(self):
        if len(self.weights) != 4 or any(
            type(weight) not in (int, float) or not isfinite(weight) for weight in self.weights
        ):
            raise ValueError("Expected four finite evaluation weights")

    def __call__(self, board, side):
        value = fsum(weight * feature for weight, feature in zip(self.weights, model_features(board)))
        return value if side == "D" else -value


def load_evaluator(path, *, candidate=False):
    """Load a saved model. Null weights select the hand-tuned baseline."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Expected a version 1 training checkpoint")
    selection = "candidate" if candidate else "best"
    try:
        weights = data[selection]["weights"]
        return None if weights is None else LinearEvaluator(tuple(weights))
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Checkpoint has no valid {selection} model") from exc


def fit_evaluator(rows, regularization=1.0):
    """Fit ridge regression to (pressure, escapes, material, intercept, result) rows."""
    if not rows or regularization <= 0:
        raise ValueError("Training needs samples and positive regularization")
    size = 4
    system = [
        [fsum(row[i] * row[j] for row in rows) + (regularization if i == j else 0)
         for j in range(size)] + [fsum(row[i] * row[-1] for row in rows)]
        for i in range(size)
    ]
    # The positive ridge penalty makes this small normal-equation matrix invertible.
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(system[row][column]))
        system[column], system[pivot] = system[pivot], system[column]
        scale = system[column][column]
        system[column] = [element / scale for element in system[column]]
        for index, row in enumerate(system):
            if index != column:
                factor = row[column]
                system[index] = [element - factor * base for element, base in zip(row, system[column])]
    return LinearEvaluator(tuple(row[-1] for row in system))
