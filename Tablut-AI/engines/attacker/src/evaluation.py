"""Hand-tuned baseline and optional eight-feature evolutionary evaluator.

Schema 2 models carry eight weights. Legacy schema-1 models (six features, V2-V4) are
still loadable: they are padded with two zeros, which is behaviour-preserving because
the two new features are zero-initialised in ``BASE_WEIGHTS`` as well.
"""
from dataclasses import dataclass
import json
from math import fsum,isfinite
from pathlib import Path
from config.settings import ATTACKER_WEIGHTS,DEFENDER_WEIGHTS
from src.features import basic_features,extract_features,FEATURE_NAMES

SCHEMA_VERSION = 2
LEGACY_FEATURES = FEATURE_NAMES[:6]


def migrate_weights(weights):
    """Return an eight-gene vector; pad legacy six-gene models with zeros."""
    values=tuple(weights)
    if len(values)==len(FEATURE_NAMES):
        return values
    if len(values)==len(LEGACY_FEATURES):
        return values+(0.0,)*(len(FEATURE_NAMES)-len(LEGACY_FEATURES))
    raise ValueError(f"Expected {len(FEATURE_NAMES)} weights (or {len(LEGACY_FEATURES)} legacy ones)")


def evaluate_attacker(board):
    pressure,escapes,material=basic_features(board)
    w=ATTACKER_WEIGHTS
    return w["king_pressure"]*pressure+w["king_escape_risk"]*escapes+w["piece_advantage"]*material

def evaluate_defender(board):
    pressure,escapes,material=basic_features(board)
    w=DEFENDER_WEIGHTS
    return -w["king_safety"]*pressure+w["escape_routes"]*escapes-w["piece_advantage"]*material

@dataclass(frozen=True)
class WeightedEvaluator:
    weights: tuple
    migrated: bool = False

    def __post_init__(self):
        if len(self.weights)!=len(FEATURE_NAMES) or any(type(w) not in (int,float) or not isfinite(w) or abs(w)>10000 for w in self.weights):
            raise ValueError(f"Expected {len(FEATURE_NAMES)} finite weights with absolute value <= 10000")

    def __call__(self,board,side):
        if side not in ("A","D"):
            raise ValueError("Side must be A or D")
        score=fsum(w*f for w,f in zip(self.weights,extract_features(board, escape_distance=bool(self.weights[6]), king_threat=bool(self.weights[7]))))
        return score if side=="D" else -score

def load_evaluator(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict) or data.get("model_type")!="evolutionary_dynamic":
        raise ValueError("Expected an evolutionary_dynamic model")
    schema=data.get("schema_version")
    if schema==SCHEMA_VERSION:
        if data.get("features")!=list(FEATURE_NAMES):
            raise ValueError("Schema-2 models need the eight features in order")
        return WeightedEvaluator(tuple(data["weights"]))
    if schema==1:
        if data.get("features")!=list(LEGACY_FEATURES):
            raise ValueError("Schema-1 models need the six legacy features in order")
        if len(data["weights"])!=len(LEGACY_FEATURES):
            raise ValueError("Schema-1 models need exactly six weights")
        return WeightedEvaluator(migrate_weights(tuple(data["weights"])),True)
    raise ValueError(f"Unsupported model schema: {schema!r}")

def model_record(weights,**metadata):
    evaluator=WeightedEvaluator(migrate_weights(tuple(weights)))
    return dict(schema_version=SCHEMA_VERSION,model_type="evolutionary_dynamic",
                features=list(FEATURE_NAMES),weights=evaluator.weights,metadata=metadata)
