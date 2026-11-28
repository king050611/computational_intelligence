"""Run or resume the attacker's two-stage genetic training."""
import argparse
from hashlib import sha256
import json
from zipfile import ZIP_DEFLATED, ZipFile
from pathlib import Path

from scripts.train_role import main as train_role
from src.role_player import ROOT, role_spec
from src.evolution import training_lock


def archive_completed(run, archive_dir):
    """Move settled candidate outputs only after a byte-verified external backup."""
    with training_lock(run):
        checkpoints = sorted(run.glob("checkpoint-*.json"))
        if len(checkpoints) < 2:
            return
        latest = json.loads(checkpoints[-1].read_bytes())["generation"]
        for number in range(latest + 1):
            generation = run / f"g{number:04}"
            checkpoint = run / f"checkpoint-{number:04}.json"
            files = list(generation.rglob("*")) if generation.is_dir() else []
            files = [file for file in files if file.is_file() and not file.is_symlink()]
            if checkpoint in checkpoints[:-2]:
                files.append(checkpoint)
            if not files:
                continue
            archive_dir.mkdir(parents=True, exist_ok=True)
            metrics = json.loads(checkpoint.read_bytes()) if checkpoint.exists() else None
            if metrics is not None and number:
                (run / f"generation-{number:04}.json").write_text(
                    json.dumps({key: metrics[key] for key in ("generation","points_floor","quick","final")},
                               indent=2), encoding="utf-8")
            archive = archive_dir / f"g{number:04}.zip"
            if archive.exists():
                # An older checkpoint may become eligible on a later invocation.
                archive = archive_dir / f"g{number:04}-checkpoint.zip"
            hashes = {path.relative_to(run).as_posix(): sha256(path.read_bytes()).hexdigest()
                      for path in files}
            with ZipFile(archive,"x",ZIP_DEFLATED) as bundle:
                for name in hashes:
                    bundle.write(run / name,name)
                bundle.writestr("SHA256.json",json.dumps(hashes,indent=2))
            with ZipFile(archive) as bundle:
                if any(sha256(bundle.read(name)).hexdigest()!=digest for name,digest in hashes.items()):
                    raise RuntimeError(f"Archive validation failed: {archive}")
            for name,digest in hashes.items():
                path=run / name
                if sha256(path.read_bytes()).hexdigest()==digest:
                    path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/training.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/training/attacker")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--archive-to", type=Path, help="Verified backup of completed round data")
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    protected = (ROOT / "models").resolve(), (ROOT / "engines").resolve()
    if any(output == path or path in output.parents for path in protected):
        parser.error("Use a separate run directory for training output")
    if args.archive_to:
        archive_dir=args.archive_to.resolve()
        if archive_dir==output or output in archive_dir.parents or any(archive_dir==p or p in archive_dir.parents for p in protected):
            parser.error("Archive to a separate directory outside the run, engines and models")
    role_spec("D")
    candidate = role_spec("A")
    settings = json.loads(args.config.read_bytes())
    flags = ["--opponent-pool", str(ROOT / "config/defender_pool.json"),
             "--candidate-engine", candidate["engine"], "--initial-model", candidate["model"],
             "--output-dir", str(output)]
    for key, flag in (("initial_population", "--initial-population"),
                      ("mutation_groups", "--mutation-groups")):
        value = settings.get(key)
        if not value:
            continue
        path = (ROOT / value).resolve()
        if any(path == protected_path or protected_path in path.parents for protected_path in protected):
            parser.error(f"{key} must live outside models/ and engines/")
        flags += [flag, str(path)]
    train_role("attacker", flags + (["--resume"] if args.resume else []), settings=settings)
    if args.archive_to:
        archive_completed(output,archive_dir)


if __name__ == "__main__":
    main()
