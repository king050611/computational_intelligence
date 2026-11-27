"""Prepare reproducible Phase 4 research inputs without starting timed games."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

from scripts.analyze_history import write_jsonl
from scripts.build_strategy_dataset import read_rows, symmetry
from scripts.generate_research_games import fingerprint
from src.evaluation import model_record
from config.evolution import BASE_WEIGHTS


def main():
    out=Path("reports/phase4")
    out.mkdir(parents=True,exist_ok=False)
    archive=out/"v6_995c56b.zip"
    subprocess.run(["git","archive","--format=zip",f"--output={archive}","995c56b","--","src","config","TeamXX.py","reference/Tablut.py"],check=True)
    models=out/"models"
    models.mkdir()
    champion=Path("reports/historical_analysis/v4_champion_schema2.json")
    shutil.copyfile(champion,models/"champion.json")
    for name in ("aggressive","blockade","escape","protective"):
        shutil.copyfile(Path("reports/phase3/models")/f"{name}.json",models/f"{name}.json")
    (models/"manual.json").write_text(json.dumps(model_record(BASE_WEIGHTS),indent=2),encoding="utf-8")
    provenance={p.as_posix():sha256(p.read_bytes()).hexdigest()
                for p in [archive,*models.glob("*.json"),Path("reports/training/v4_champion_archive/best.json")]}
    frozen={v:fingerprint(Path("reports/phase3/engines")/v) for v in ("v3","v4","v5","v6")}
    provenance["engines"]=frozen
    (out/"frozen_manifest.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
    for role,side,names in (("attacker","D",("escape","protective")),("defender","A",("aggressive","blockade"))):
        pool=[dict(name=name,side=side,share=share,model=f"models/{name}.json",
              model_sha256=provenance[(models/f"{name}.json").as_posix()],depth=4,seconds=60)
              for name,share in zip((*names,"champion","manual"),(30,30,25,15))]
        (out/f"{role}_pool.json").write_text(json.dumps(pool,indent=2),encoding="utf-8")
    split_tactics(out)


def split_tactics(out):
    cases=read_rows(Path("data/positions/phase3/tactical_positions.jsonl"))
    splits={name:[] for name in ("development","regression","holdout")}
    targets=dict(development=.70,regression=.15,holdout=.15)
    seen=set()
    groups={}
    for row in cases:
        key=symmetry(row["board"],row["side"])
        if key in seen:
            raise ValueError("Tactical source already contains equivalent boards")
        seen.add(key)
        groups.setdefault(row["synthetic_playout"],[]).append(row)
    for rows in sorted(groups.values(),key=len,reverse=True):
        name=max(splits,key=lambda k:targets[k]*len(cases)-len(splits[k]))
        splits[name].extend(rows)
    for name,rows in splits.items():
        write_jsonl(out/"tactics"/f"{name}.jsonl",rows)
    print({k:len(v) for k,v in splits.items()})


if __name__=="__main__":
    main()
