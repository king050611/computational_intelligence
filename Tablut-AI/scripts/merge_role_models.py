"""Package two frozen Schema-2 specialists for the existing evolutionary player."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from src.evaluation import load_evaluator, WeightedEvaluator
from src.features import FEATURE_NAMES


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("attacker","defender","output"):
        parser.add_argument(name,type=Path)
    args=parser.parse_args()
    record=dict(schema_version=3,model_type="dual_role_evolutionary_dynamic",
                features=list(FEATURE_NAMES),metadata=dict(source_commit=subprocess.check_output(
                    ["git","rev-parse","HEAD"],text=True).strip()))
    for side in ("attacker","defender"):
        path=getattr(args,side)
        if json.loads(path.read_bytes()).get("schema_version")!=2:
            parser.error("Each specialist must use Schema 2")
        evaluator=load_evaluator(path)
        if not isinstance(evaluator,WeightedEvaluator):
            parser.error("Expected a single-role input")
        record[side+"_weights"]=evaluator.weights
        record["metadata"][side+"_model_sha256"]=sha256(path.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as file:
        json.dump(record,file,indent=2)


if __name__=="__main__":
    main()
