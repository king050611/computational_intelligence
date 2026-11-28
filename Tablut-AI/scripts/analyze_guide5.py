"""Summarize Guide 5's matched frozen-defender experiments after completion."""
from collections import Counter
import json
from pathlib import Path
from random import Random
from statistics import mean

from scripts.analyze_history import normalize_replay
from scripts.generate_research_games import ROOT

OUT = ROOT / "reports/experiments/guide5"


def read(path):
    return json.loads(path.read_bytes())


def measure(rows):
    counts = Counter(row["result"]["winner"] for row in rows.values())
    turns = [event for row in rows.values() for event in row["moves"] if event["player"] == "A"]
    stats = [event["search"] for event in turns if event.get("search")]
    proofs = Counter(s.get("capture_proof", "not_started") for s in stats)
    ties = Counter(s.get("tie_research", "not_started") for s in stats)
    candidate_depths = Counter(str(s["candidate_depth"]) for s in stats if s.get("candidate_depth"))
    full_depths = [s.get("full_width_depth", s["completed_depth"]) for s in stats]
    return dict(
        games=len(rows), wins=counts["A"], draws=counts["DRAW"], losses=counts["D"],
        win_rate=counts["A"]/len(rows), point_rate=(2*counts["A"]+counts["DRAW"])/(2*len(rows)),
        attacker_turns=len(turns), search_samples=len(stats), proofs=dict(proofs),
        proof_plies=Counter(str(len(s["pv"])) for s in stats if s.get("capture_proof") == "WIN"),
        tie_attempts=len(stats)-ties["not_started"], tie_changes=sum(s.get("tie_changed_move",False) for s in stats),
        candidate_depths=candidate_depths, full_width_depth=mean(full_depths),
        mean_attacker_turn_seconds=mean(move["elapsed_seconds"] for move in turns),
        max_attacker_seconds=max(row["attacker_seconds"] for row in rows.values()),
        max_defender_seconds=max(row["defender_seconds"] for row in rows.values()),
        illegal_moves=0, referee_timeouts=0, exceptions=0,
    )


def paired(base, model):
    points = {"A": 2,"DRAW": 1,"D": 0}
    changes, differences = Counter(), []
    for opening, row in base.items():
        before, after = row["result"]["winner"], model[opening]["result"]["winner"]
        changes[f"{before}->{after}"] += 1
        differences.append((int(after=="A")-int(before=="A"),(points[after]-points[before])/2))
    rng = Random(91234)
    win, score = [], []
    for _ in range(5000):
        sample = rng.choices(differences,k=len(differences))
        win.append(mean(a for a,_ in sample))
        score.append(mean(b for _,b in sample))
    return dict(changes=changes,win_rate_difference=mean(a for a,_ in differences),
                point_rate_difference=mean(b for _,b in differences),
                win_rate_ci95=[sorted(win)[125],sorted(win)[4874]],
                point_rate_ci95=[sorted(score)[125],sorted(score)[4874]])


def main():
    base=ROOT/"reports/v7_attacker_base_20"
    opening_manifest=read(base/"manifest.json")
    originals=opening_manifest["openings"]
    boards={r["id"]:r["board"] for r in originals}
    reports, sets = {}, {}
    for label, folder in {"V5":base, **{k:OUT/k for k in ("R0","R1","R2")}}.items():
        current=read(folder/"manifest.json")
        if current["candidate_side"]!="A" or current["specs"][1]!=opening_manifest["specs"][1]:
            raise ValueError(f"{label}: mismatched frozen defense")
        if set(folder.glob("individual/rejected/*.json")):
            raise ValueError(f"{label}: rejected matches")
        data=read(folder/"games.json")["games"]
        rows={row["opening_id"]:row for row in data}
        if len(data)!=20 or rows.keys()!=boards.keys():
            raise ValueError(f"{label}: incomplete or unmatched openings")
        for opening, row in rows.items():
            if (row["initial_board"]!=boards[opening] or not normalize_replay(row)[0]
                or max(row["attacker_seconds"],row["defender_seconds"])>60):
                raise ValueError(f"{label}: failed replay, opening {opening}")
        sets[label]=rows
        reports[label]=measure(rows)
    reports["paired_vs_R0"]={label:paired(sets["R0"],sets[label]) for label in ("R1","R2")}
    reports["paired_vs_V5"]={label:paired(sets["V5"],sets[label]) for label in ("R0","R1","R2")}
    (OUT/"summary.json").write_text(json.dumps(reports,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(reports,indent=2))


if __name__ == "__main__":
    main()
