"""Hand-tuned baseline and optional six-feature evolutionary evaluator."""
from dataclasses import dataclass
import json
from math import fsum,isfinite
from pathlib import Path
from config.settings import ATTACKER_WEIGHTS,DEFENDER_WEIGHTS
from src.features import basic_features,extract_features,FEATURE_NAMES

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

    def __post_init__(self):
        if len(self.weights)!=6 or any(type(w) not in (int,float) or not isfinite(w) or abs(w)>10000 for w in self.weights):
            raise ValueError("Expected six finite weights with absolute value <= 10000")

    def __call__(self,board,side):
        if side not in ("A","D"):
            raise ValueError("Side must be A or D")
        score=fsum(w*f for w,f in zip(self.weights,extract_features(board)))
        return score if side=="D" else -score

def load_evaluator(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict) or data.get("model_type")!="evolutionary_dynamic" or data.get("schema_version")!=1 or data.get("features")!=list(FEATURE_NAMES):
        raise ValueError("Expected an evolutionary_dynamic six-feature model")
    return WeightedEvaluator(tuple(data["weights"]))

def model_record(weights,**metadata):
    evaluator=WeightedEvaluator(tuple(weights))
    return dict(schema_version=1,model_type="evolutionary_dynamic",features=list(FEATURE_NAMES),weights=evaluator.weights,metadata=metadata)
