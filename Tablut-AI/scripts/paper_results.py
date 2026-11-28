"""Build paper CSV and four vector figures from the verified local archives."""
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

from scripts.train_role import allocate

ROOT=Path(__file__).resolve().parents[1]
ARCHIVES=ROOT.parent/"reference/archive"
OLD="pre-cleanup-v7-701f0d0.zip"
FINAL="final-research-3a03c02.zip"
FIELDS="experiment_id commit algorithm engine role opponent games wins draws losses win_rate official_points point_rate depth_limit mean_completed_depth mean_move_seconds max_game_seconds illegal_moves timeouts exceptions source_path archive_reference limitations".split()


def read(archive,path):
    with ZipFile(ARCHIVES/archive) as bundle:
        return json.loads(bundle.read(path))


def record(rows,experiment,algorithm,engine,role,opponent,depth,archive,path,commit="NA",limitations=""):
    outcomes, depths, durations, maxima = Counter(), [], [], []
    counters={key:[] for key in ("illegal_moves","timeouts","exceptions")}
    for row in rows:
        side=row["our_side"]
        winner=row["result"]["winner"] if "result" in row else row["winner"]
        outcomes["win" if winner==side else "draw" if winner in ("DRAW",None) else "loss"]+=1
        clock=row.get("attacker_seconds" if side=="A" else "defender_seconds")
        if clock is not None: maxima.append(clock)
        if "moves" in row:
            turns=[m for m in row["moves"] if m["player"]==side]
            stats=[m["search"] for m in turns if m.get("search")]
            durations.extend(m["elapsed_seconds"] for m in turns)
            for key in counters: counters[key].append(int(row["result"].get("reason")=={"illegal_moves":"illegal_move","timeouts":"timeout","exceptions":"exception"}[key]))
        else:
            stats=(row.get("search_stats") or {}).get(side,[])
            if row.get("our_mean_move_seconds") is not None: durations.append(row["our_mean_move_seconds"])
            for key in counters:
                if key in row: counters[key].append(row[key])
        depths.extend(s.get("full_width_depth",s["completed_depth"]) for s in stats if "completed_depth" in s)
    n=len(rows)
    w,d,l=(outcomes[k] for k in ("win","draw","loss"))
    return dict(experiment_id=experiment,commit=commit,algorithm=algorithm,engine=engine,role=role,opponent=opponent,
                games=n,wins=w,draws=d,losses=l,win_rate=w/n,official_points=2*w+d,point_rate=(2*w+d)/(2*n),
                depth_limit=depth,mean_completed_depth=mean(depths) if depths else "NA",
                mean_move_seconds=mean(durations) if durations else "NA",max_game_seconds=max(maxima,default="NA"),
                **{k:sum(v) if len(v)==n else "NA" for k,v in counters.items()},
                source_path=path,archive_reference=f"{archive}::{path}",limitations=limitations)


def build():
    rows=[]
    historical=(
        ("F1","V4","V4",4,"evolution_v5_formal_validation_20261129/v4_champion_vs_v3_formal_60"),
        ("F1","V5","V5",4,"v5_strength_20261202/v5_engine_vs_v3_formal_60"),
        *(("F2",f"Depth {d}","historical champion",d,f"v5_depth_study_20261130/champion_vs_control_depth{d}") for d in (4,5,6)),
    )
    for group,name,engine,depth,relative in historical:
        path=f"reports/experiments/{relative}.json"
        data=read(OLD,path)
        rows.append(record(data["results"],group,name,engine,"paired","V3 formal",depth,OLD,path,
                           data["manifest"]["commit_sha"],"Exchanged roles; unweighted mean of per-game turn means."))
    series={"V5":"reports/v7_attacker_base_20","E1":"reports/v7_attacker_e1_20",
            **{k:f"reports/experiments/guide5/{k}" for k in ("R0","R1","R2")}}
    for name,folder in series.items():
        path=f"{folder}/games.json"
        rows.append(record(read(FINAL,path)["games"],"F3",name,"V5" if name in ("V5","E1") else "V5 + R0","A",
                           "D-Champion-01",4,FINAL,path,limitations="Same 20 starting boards; historical wall-clock run."))
    for defender in ("champion","escape","protective"):
        summary_path="reports/v7_attacker/screen/summary.json"
        data=read(OLD,summary_path)
        for variant in data:
            path=f"reports/v7_attacker/screen/{variant}/{defender}/games.json"
            segment=read(OLD,path)["games"]
            rows.append(record([dict(g,our_side="D") for g in segment],
                "defender_screen",defender,"V7","D",variant,4,OLD,path,
                limitations="Opening schedule differs by defender."))
    train="reports/training/v7_attacker_weights"
    manifest=read(FINAL,f"{train}/config.json")
    population=read(FINAL,"reports/v7_weights/population.json")
    checkpoint=read(FINAL,f"{train}/checkpoint-0001.json")
    for stage in ("quick","final"):
        for i,trial in enumerate(checkpoint[stage]):
            label=next((f"P{j}" for j,w in enumerate(population) if w==trial["weights"]),
                       "P0 exact" if trial["weights"]==checkpoint["quick"][0]["weights"] else "unmatched")
            if label=="P0": label="P0 rounded"
            path=f"{train}/g0001/{stage}_{i:02}/games.json"
            games=read(FINAL,path)["games"]
            opponents=allocate(manifest["pool"],len(games))
            for j,opponent in enumerate(manifest["pool"]):
                subset=[g for g,k in zip(games,opponents) if k==j]
                if subset:
                    rows.append(record(subset,"F4" if stage=="final" else "training_quick",label,
                        "V5 + R0","A",opponent["name"],4,FINAL,path,limitations="P7 absent; opponent assignments follow the saved pool quota."))
    return rows


def figures(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    folder=ROOT/"reports/figures"
    folder.mkdir(exist_ok=True)
    for i in range(1,5):
        section=[r for r in rows if r["experiment_id"]==f"F{i}"]
        groups={}
        for row in section:
            counts=groups.setdefault(row["algorithm"],[0,0,0])
            for j,key in enumerate(("wins","draws","losses")): counts[j]+=int(row[key])
        labels=list(groups)
        fig,ax=plt.subplots(figsize=(7.6,4.2),layout="constrained")
        bottom=[0.0]*len(labels)
        for j,(name,color) in enumerate(zip(("Wins","Draws","Losses"),("#007d69","#9aa4ad","#b14c46"))):
            part=[100*groups[k][j]/sum(groups[k]) for k in labels]
            ax.bar(labels,part,bottom=bottom,label=name,color=color)
            bottom=[a+b for a,b in zip(bottom,part)]
        score=ax.twinx()
        score.plot(labels,[100*(w+d/2)/(w+d+l) for w,d,l in groups.values()],"o--",color="#172835",label="Official points")
        score.set_ylim(0,105)
        score.set_ylabel("Official points rate (%)")
        ax.set_ylim(0,105)
        ax.set_ylabel("Share of games (%)")
        ax.legend(loc="upper center",bbox_to_anchor=(.5,1.15),ncols=3,frameon=False)
        fig.savefig(folder/f"figure_{i}.pdf")
        plt.close(fig)


def main():
    path=ROOT/"reports/results.csv"
    import sys
    if sys.argv[1:]==["--figures-only"]:
        with path.open(encoding="utf-8",newline="") as f:
            figures(list(csv.DictReader(f)))
        return
    rows=build()
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    figures(rows)


if __name__=="__main__":
    main()
