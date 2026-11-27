"""Freeze and run the finite Phase 3 matrix."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

from src.evaluation import model_record

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs",type=int,default=10)
    parser.add_argument("--pressure-games",type=int,default=20)
    parser.add_argument("--root",type=Path,default=Path("reports/phase3"))
    args=parser.parse_args()
    out=args.root
    out.mkdir(parents=True,exist_ok=True)
    training=Path("reports/training")
    history=Path("reports/historical_analysis")
    models=out/"models"
    models.mkdir(exist_ok=True)
    engines=out/"engines"
    engines.mkdir(exist_ok=True)
    for version,archive in (("v3","v3_baseline_archive"),("v4","v4_engine_archive")):
        target=engines/version
        if not target.exists():
            shutil.copytree(training/archive/"engine",target,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    for version in ("v5","v6"):
        target=engines/version
        if not target.exists():
            archive=history/"v5_ff7e4c5.zip" if version=="v5" else out/"v6_87e3119.zip"
            if version=="v6":
                subprocess.run(["git","archive","--format=zip",f"--output={archive}","87e3119","--","src","config","TeamXX.py","reference/Tablut.py"],check=True)
            with ZipFile(archive) as z:
                z.extractall(target)
    for name,source in (("v3",training/"v3_baseline_archive/v3_champion_best.json"),
                        ("v4",training/"v4_champion_archive/best.json"),
                        ("champion",history/"v4_champion_schema2.json")):
        target=models/(name+".json")
        if not target.exists():
            shutil.copyfile(source,target)
    styles={
        "aggressive":(-620,600,-130,0,4,0,0,-160),
        "blockade":(-345,820,-168,0,45,-175,-115,0),
        "escape":(-300,900,-145,-60,50,-35,-125,0),
        "protective":(-620,600,-205,0,38,-55,0,-180),
    }
    for name,weights in styles.items():
        target=models/(name+".json")
        if not target.exists():
            target.write_text(json.dumps(model_record(weights, untrained_style=name),indent=2),encoding="utf-8")
    matrix=[
        ("v3_v4","v3","v3","v4","v4",4,4,0,60,None,args.pairs),
        ("v4_v5","v4","v4","v5","champion",4,4,0,60,None,args.pairs),
        ("v5_v6","v5","champion","v6","champion",4,4,0,60,None,args.pairs),
        ("champion_manual","v6","champion","v6",None,4,4,0,60,None,args.pairs),
        ("depth4_depth5","v6","champion","v6","champion",4,5,0,60,None,args.pairs),
        ("standard_reference","v6","champion","v6","champion",4,5,50000,90,None,args.pairs),
    ]
    matrix.extend((name,"v6",style,"v6","champion",4,4,0,60,side,args.pressure_games)
        for name,style,side in (("aggressive_pressure","aggressive","A"),("blockade_pressure","blockade","A"),
                                ("escape_pressure","escape","D"),("protective_pressure","protective","D")))
    for i,(name,av,am,bv,bm,ad,bd,bn,seconds,side,pairs) in enumerate(matrix):
        path=out/"matches"/name
        command=[sys.executable,"-u","-m","scripts.generate_research_games","--output",str(path),
                 "--pairs",str(pairs),"--seed",str(180127+i),"--seconds",str(seconds),
                 "--candidate-engine",str(engines/av),"--control-engine",str(engines/bv),
                 "--candidate-depth",str(ad),"--control-depth",str(bd),"--control-nodes",str(bn)]
        for flag,model in (("--candidate-model",am),("--control-model",bm)):
            if model:
                command.extend([flag,str(models/(model+".json"))])
        if side:
            command.extend(["--candidate-side",side])
        if path.exists():
            command.append("--resume")
        subprocess.run(command,check=True)
        if name in ("standard_reference","protective_pressure") and out==Path("reports/phase3"):
            subprocess.run([sys.executable,"-m","scripts.analyze_phase3"],check=True)

if __name__=="__main__":
    main()
