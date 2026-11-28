"""Build a local V1–V5 corpus without modifying source artifacts."""
import csv
import hashlib
import json
import re
import sys
import subprocess
from io import BytesIO
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile, BadZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.game import apply_move, check_winner, get_state_key, parse_board

OUT = ROOT / "reports/historical_analysis"
POSITIONS = ROOT / "data/positions"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def version_of(path):
    # The benchmark's "version": "3.0" is its output schema, not the engine version.
    if "/linear_" in path or "linear_selfplay" in path:
        return "legacy_or_unknown"
    match = re.search(r"(?:^|[/_])v([1-5])(?=[_/\.])", path.lower())
    if match:
        return f"V{match[1]}"
    if "evolution_quick_20261125" in path:
        return "V1"
    return "legacy_or_unknown"


def outcome(row):
    result = row.get("result")
    winner = row.get("winner", result.get("winner") if isinstance(result, dict) else None)
    log = row.get("log", row.get("referee_log", ""))
    if not isinstance(log, str):
        log = ""
    counters = {k: row.get(k) for k in ("illegal_moves", "timeouts", "exceptions", "invalid_returns")}
    reason = result.get("reason") if isinstance(result, dict) else None
    for pattern, name, counter in (
        ("Illegal move", "illegal_move", "illegal_moves"),
        ("exceeded time limit", "timeout", "timeouts"),
        ("Exception caught", "exception", "exceptions"),
    ):
        if (reason is None and (counters[counter] or pattern in log)):
            reason = name
    if reason is None and winner == "DRAW":
        if "Repeated position" in log:
            reason = "repetition"
        elif "cannot move" in log:
            reason = "no_legal_moves"
    fault = any(counters.values()) or reason in ("illegal_move", "timeout", "exception")
    return winner, reason, counters, fault


def normalize_replay(row):
    if not row.get("moves") or row.get("initial_board") is None:
        return False, None
    try:
        board = parse_board(row["initial_board"])
        history = []
        terminal = None
        for index, event in enumerate(row["moves"]):
            side = "A" if index % 2 == 0 else "D"
            other = "D" if side == "A" else "A"
            if terminal is not None or event["player"] != side or event.get("accepted") is not True:
                return False, "terminal or invalid event before end"
            if parse_board(event["board_before"]) != board:
                return False, "board_before mismatch"
            move = tuple(map(tuple, event["move"]))
            history.append(get_state_key(board, side))
            board = apply_move(board, move, side)
            after = tuple(map(tuple, event["board_after"]))
            # Official referee may leave '.' in the castle after capturing its king.
            if after[4][4] == "." and not any("K" in line for line in after):
                after = after[:4] + (after[4][:4] + ("X",) + after[4][5:],) + after[5:]
            if after != board:
                return False, "board_after mismatch"
            terminal = check_winner(board, other, history)
        winner, _, _, fault = outcome(row)
        return (terminal == winner and not fault), None if terminal == winner else "terminal result mismatch"
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return False, str(exc)


def embedded_runs(data):
    """Standalone training checkpoints can contain actual evaluation games."""
    for label in ("candidate", "best"):
        record = data.get(label)
        if not isinstance(record, dict):
            continue
        # The best record is copied into later checkpoints.
        if record.get("generation", data.get("generation")) != data.get("generation"):
            continue
        evaluation = record.get("evaluation")
        if isinstance(evaluation, dict) and isinstance(evaluation.get("games"), list):
            yield label, record, evaluation["games"]


def run_rows(data):
    if not isinstance(data, dict):
        return
    for name in ("results", "games"):
        rows = data.get(name)
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and (
            "winner" in rows[0] or isinstance(rows[0].get("result"), dict)
        ):
            yield name, {}, rows
            return
    yield from embedded_runs(data)


def find_model(path, name, sha, by_hash, read):
    if sha and sha in by_hash:
        return by_hash[sha], sha
    if name:
        leaf = Path(name.replace("\\", "/")).name
        sibling = path.rsplit("/", 1)[0] + "/" + leaf
        normalized = name.replace("\\", "/")
        relative = normalized.split("/Tablut-AI/", 1)[-1]
        for candidate in dict.fromkeys((sibling, "Tablut-AI/" + relative)):
            try:
                raw = read[candidate]
                model = json.loads(raw)
                if isinstance(model, dict) and "weights" in model and (not sha or digest(raw) == sha):
                    return model["weights"], digest(raw)
            except (KeyError, ValueError):
                continue
    return None, sha


def load_sources():
    raw, inventory = {}, []
    roots = (ROOT / "reports", ROOT / "reference", ROOT.parent / "reference")
    for root in roots:
        for path in sorted(root.rglob("*")):
            if OUT in path.parents or not path.is_file() or path.suffix.lower() not in {
                ".json", ".jsonl", ".log", ".zip", ".rar", ".7z", ".npz", ".html", ".md"
            }:
                continue
            relative = path.relative_to(ROOT.parent).as_posix()
            suffix = path.suffix.lower()
            data = path.read_bytes()
            inventory.append(dict(path=relative, bytes=len(data), sha256=digest(data), kind=suffix[1:]))
            if suffix == ".zip":
                try:
                    with ZipFile(path) as archive:
                        for entry in archive.infolist():
                            if Path(entry.filename).suffix.lower() in {".json", ".jsonl", ".log", ".html"}:
                                raw[f"{relative}!/{entry.filename}"] = archive.read(entry)
                except (BadZipFile, OSError) as exc:
                    inventory[-1]["error"] = str(exc)
            elif suffix in {".json", ".jsonl", ".log", ".html"}:
                raw[relative] = data
    return raw, inventory



def local_git_sources(inventory, raw):
    """Read experiment artifacts from available Git objects without checkout."""
    git_root = ROOT.parent
    candidates = subprocess.check_output(
        ["git", "rev-list", "--objects", "--all", "--", "Tablut-AI/reports"],
        cwd=git_root, encoding="utf-8",
    )
    supported = {".json", ".jsonl", ".log", ".zip", ".html"}
    objects = {}
    for line in candidates.splitlines():
        obj, _, path = line.partition(" ")
        if path.startswith("Tablut-AI/reports/") and "/historical_analysis/" not in path and Path(path).suffix in supported:
            objects[obj] = path
    if not objects:
        return
    response = subprocess.check_output(["git", "cat-file", "--batch"], cwd=git_root,
                                       input=("\n".join(objects)+"\n").encode("ascii"))
    stream = BytesIO(response)
    on_disk = {(item["path"],item["sha256"]) for item in inventory}
    for obj,path in objects.items():
        header = stream.readline().split()
        if len(header)!=3 or header[1]!=b"blob":
            continue
        data=stream.read(int(header[2]))
        stream.read(1)
        checksum=digest(data)
        if (path,checksum) in on_disk:
            continue
        name=f"git:{obj[:12]}!/{path}"
        suffix=Path(path).suffix
        inventory.append(dict(path=name, bytes=len(data), sha256=checksum, kind="git_blob"))
        if suffix==".zip":
            try:
                with ZipFile(BytesIO(data)) as archive:
                    for entry in archive.infolist():
                        if Path(entry.filename).suffix.lower() in supported-{".zip"}:
                            raw[f"{name}!/{entry.filename}"]=archive.read(entry)
            except BadZipFile as exc:
                inventory[-1]["error"]=str(exc)
        else:
            raw[name]=data

def write_jsonl(path, records):
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for item in records:
            file.write(canonical(item).decode() + "\n")


def collect():
    raw, inventory = load_sources()
    local_git_sources(inventory, raw)
    parsed, unreadable, model_by_hash = {}, [], {}
    for path, value in raw.items():
        try:
            if path.endswith(".json"):
                data = json.loads(value)
            elif path.endswith(".jsonl"):
                data = {"results": [json.loads(line) for line in value.splitlines() if line.strip()]}
            elif path.endswith(".html"):
                match = re.search(rb'<script id="data" type="application/json">\s*(\{.*?\})\s*</script>', value, re.S)
                if not match:
                    continue
                data = json.loads(match[1])
            else:
                continue
        except (ValueError, UnicodeError) as exc:
            unreadable.append({"path": path, "error": str(exc)})
            continue
        parsed[path] = data
        if isinstance(data, dict) and isinstance(data.get("weights"), list):
            model_by_hash[digest(value)] = data["weights"]

    matches, duplicate_count = {}, 0
    for path, data in parsed.items():
        if not isinstance(data, dict):
            continue
        manifest = data.get("manifest") or {}
        options = manifest.get("options") or {}
        for label, embedded_model, rows in run_rows(data):
            # Timing/log/board rows identify copies even when wrapped by another archive.
            # The run timestamp keeps independent repeats separate when available.
            run_key = digest(canonical([manifest.get("created_at", data.get("created_at")), rows]))
            for ordinal, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                key = f"{run_key[:24]}:{ordinal+1}"
                if key in matches:
                    duplicate_count += 1
                    matches[key]["sources"].append(path)
                    if matches[key]["version"] == "legacy_or_unknown":
                        matches[key]["version"] = version_of(path)
                    continue
                winner, reason, faults, fault = outcome(row)
                complete, problem = normalize_replay(row)
                status = ("invalid" if fault or problem or winner not in ("A", "D", "DRAW")
                          else "complete" if complete else "summary_only")
                side = row.get("our_side", row.get("greedy_side"))
                move_stats = row.get("search_stats") or {}
                if not move_stats and complete:
                    move_stats = {s: [event.get("search") for event in row["moves"] if event["player"] == s]
                                  for s in ("A", "D")}
                model_sha = (manifest.get("model_sha256") or {}).get("model")
                weights, model_sha = find_model(path, data.get("model"), model_sha, model_by_hash, raw)
                stage = ("quick" if re.search(r"/quick[_/]", path) else
                         "final" if re.search(r"/final[_/]", path) and "/training/" in path else
                         "training" if "/training/" in path or label in ("candidate", "best") else
                         "ablation" if "ablat" in path.lower() else
                         "depth_comparison" if "depth_study" in path else
                         "independent" if any(x in path for x in ("validation", "holdout", "confirm", "strength")) else
                         "replay" if complete else "experiment")
                player_strategies = row.get("strategies") or {}
                opponent_side = "D" if side == "A" else "A" if side == "D" else None
                if complete and winner == "DRAW" and reason is None:
                    reason = "unknown_draw"
                matches[key] = dict(
                    game_id=key, game_number=row.get("game", ordinal+1), version=version_of(path),
                    commit=manifest.get("commit_sha", data.get("source_commit")),
                    source_hash=manifest.get("source_hash", data.get("source_hash")),
                    experiment=path, sources=[path], stage=stage,
                    model_weights=weights if weights is not None else embedded_model.get("weights"),
                    model_sha256=model_sha, strategy=data.get("strategy", player_strategies.get(side)),
                    opponent=row.get("opponent", data.get("opponent", player_strategies.get(opponent_side))),
                    our_side=side, opening_id=row.get("opening_id"), seed=row.get("seed"),
                    run_seed=data.get("seed"), max_depth=options.get("max_depth"), options=options,
                    search_stats=move_stats, moves=row.get("moves"), initial_board=row.get("initial_board"),
                    final_board=row.get("final_board"), attacker_seconds=row.get("attacker_seconds"),
                    defender_seconds=row.get("defender_seconds"), plies=row.get("plies", row.get("accepted_moves")),
                    winner=winner, termination=reason, repetition=reason == "repetition" if reason else None,
                    faults=faults, side_issues=row.get("issues"), log=row.get("log", row.get("referee_log")),
                    quality=status, validation_error=problem, training_status="unknown")
    # Individual batches can finish even when their enclosing generation/run stops.
    completed = set()
    for path, data in parsed.items():
        if not isinstance(data, dict) or "generation" not in data or not data.get("generation"):
            continue
        parent = path.rsplit("/", 1)[0]
        screen = data.get("screening") or {}
        for trial in ((data.get("trials") or []) + screen.get("quick_trials", []) + screen.get("final_trials", [])):
            refs = trial.get("results") or ([trial["result"]] if isinstance(trial.get("result"), str) else [])
            completed.update(parent + "/" + ref.replace("\\", "/") for ref in refs if isinstance(ref, str))
    for item in matches.values():
        if item["stage"] in ("quick", "final", "training"):
            item["training_status"] = ("checkpointed" if any(p in completed for p in item["sources"])
                                       or "checkpoint-" in item["experiment"] else
                                       "interrupted_run" if "/training/evolution_v1/" in item["experiment"] else
                                       "completed_match_without_linked_checkpoint")
    partial = []
    for path, value in raw.items():
        if not path.endswith(".log"):
            continue
        log = value.decode("utf-8", errors="replace")
        games = re.findall(r"^Game (\d+)/(\d+): ([AD]) vs (A|D|DRAW)\s*$", log, re.M)
        if games and int(games[-1][0]) < int(games[-1][1]):
            origin = path.rsplit("!/", 1)[-1].removeprefix("Tablut-AI/")
            fingerprint = digest(canonical([origin, games]))
            if fingerprint not in {i["fingerprint"] for i in partial}:
                partial.append(dict(source=path, completed_log_lines=len(games), planned=int(games[-1][1]),
                                    fingerprint=fingerprint, progress=games))
    return list(matches.values()), inventory, duplicate_count, unreadable, partial


def group_statistics(rows):
    groups = defaultdict(list)
    for row in rows:
        if row["quality"] != "invalid":
            groups[row["version"], row["stage"], row["strategy"], row["opponent"], row["max_depth"],
                   row["options"].get("node_budget"), row["our_side"]].append(row)
    for key, games in sorted(groups.items(), key=lambda entry: repr(entry[0])):
        wins = sum(g["winner"] == g["our_side"] for g in games)
        draws = sum(g["winner"] == "DRAW" for g in games)
        depths = [x["completed_depth"] for g in games for x in g["search_stats"].get(g["our_side"], [])
                  if isinstance(x, dict) and isinstance(x.get("completed_depth"), int)]
        yield dict(zip(("version", "stage", "strategy", "opponent", "depth", "node_budget", "side"), key),
                   games=len(games), wins=wins if key[-1] else None, draws=draws,
                   losses=len(games)-wins-draws if key[-1] else None,
                   win_rate=wins/len(games) if key[-1] else None,
                   repetition_draws=sum(g["repetition"] is True for g in games),
                   draw_reason_unknown=sum(g["winner"]=="DRAW" and g["termination"] is None for g in games),
                   early_losses=sum(g["winner"] not in ("DRAW",g["our_side"]) and (g["plies"] or 999)<20
                                    for g in games) if key[-1] else None,
                   complete=sum(g["quality"] == "complete" for g in games),
                   mean_completed_depth=sum(depths)/len(depths) if depths else None)


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    rows, inventory, duplicates, unreadable, partial = collect()
    write_jsonl(OUT/"historical_games.jsonl", rows)
    stats = list(group_statistics(rows))
    with (OUT/"version_comparison.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, list(stats[0]))
        writer.writeheader()
        writer.writerows(stats)
    manifest = dict(quality=Counter(r["quality"] for r in rows),
                    version_quality={v: Counter(r["quality"] for r in rows if r["version"] == v)
                                     for v in sorted({r["version"] for r in rows})},
                    source_inventory=inventory, copied_game_rows=duplicates, bad_json=unreadable,
                    partial_logs=partial, unmapped_versions=sum(r["version"] == "legacy_or_unknown" for r in rows),
                    checkpoints=sum(Path(s["path"]).name.startswith("checkpoint-") for s in inventory),
                    non_json_inputs="Log fragments are inventory only. Binary models and reference archives are not matches.")
    (OUT/"dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(dict(quality=manifest["quality"], version=manifest["version_quality"], copies=duplicates,
               sources=len(inventory), partial_logs=len(partial), bad_json=len(unreadable)))


if __name__ == "__main__":
    main()
