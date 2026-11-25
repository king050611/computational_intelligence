"""Train a Tablut evaluator by self-play and save one checkpoint per iteration."""
import argparse
from collections import Counter
import contextlib
import io
from itertools import count
import json
import os
from pathlib import Path
from random import Random
import sys
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "reference")]

from Tablut import Tablut
from config.settings import DEFENDER_WEIGHTS
from scripts.benchmark import StrategyBot, Timed, standings
from src.game import apply_move, check_winner, get_legal_moves, get_state_key, initial_board
from src.learning import LinearEvaluator, fit_evaluator, model_features
from src.search import choose_move


OPPONENTS = ("greedy", "minimax")
REPLAY_ITERATIONS = 3
HISTORICAL_MODELS = 8
DEFAULTS = dict(seed=42, train_games=16, eval_pairs=3, max_plies=160)
STOP_FILE = "STOP"


def other_side(side):
    return "D" if side == "A" else "A"


def play_training_game(evaluators, rng, max_plies):
    """Play at fixed depth for repeatability and label positions with the real result."""
    board, side = initial_board(), "A"
    path, samples = [], []
    for ply in range(max_plies + 1):
        result = check_winner(board, side, path)
        if result:
            score = {"A": -1, "DRAW": 0, "D": 1}[result]
            return result, [features + (score,) for features in samples]
        if ply == max_plies:
            break
        samples.append(model_features(board))
        if ply < 6 or rng.random() < 0.10:
            move = rng.choice(get_legal_moves(board, side))
        else:
            move = choose_move(board, side, strategy="minimax", evaluator=evaluators[side],
                               history=path)
        path.append(get_state_key(board, side))
        board, side = apply_move(board, move, side), other_side(side)
    return "truncated", []


def opening_board(seed, pair):
    rng = Random(f"{seed}:evaluation:{pair}")
    board = initial_board()
    # An even number of quiet opening plies leaves the attacker on move.
    for side in ("A", "D", "A", "D"):
        move = rng.choice(get_legal_moves(board, side))
        board = apply_move(board, move, side)
        if check_winner(board, other_side(side)):
            return initial_board()
    return board


def evaluate(evaluator, config):
    """Score a model on fixed paired openings under the official referee's clock."""
    rows = []
    for pair in range(config["eval_pairs"]):
        board = opening_board(config["seed"], pair)
        for opponent in OPPONENTS:
            for side in ("A", "D"):
                learner = Timed(StrategyBot("minimax", config["seed"], evaluator=evaluator))
                baseline = Timed(StrategyBot(opponent, config["seed"]))
                attacker, defender = (learner, baseline) if side == "A" else (baseline, learner)
                game = Tablut()
                game.board = [list(row) for row in board]
                with contextlib.redirect_stdout(io.StringIO()) as log:
                    game.play(attacker, defender)
                # Failures in either player invalidate this evaluation run.
                message = log.getvalue()
                if (attacker.errors or defender.errors or attacker.invalid_returns or defender.invalid_returns
                        or "exceeded time limit" in message or "Illegal move" in message):
                    raise RuntimeError(f"Evaluation game failed for pair {pair}, {opponent}, {side}")
                rows.append(dict(our_side=side, winner=game.winner or "DRAW", opponent=opponent,
                                 pair=pair, attacker_seconds=sum(attacker.times),
                                 defender_seconds=sum(defender.times)))
    return dict(**standings(rows), by_opponent={
        opponent: standings([row for row in rows if row["opponent"] == opponent])
        for opponent in OPPONENTS
    }, games=rows)


def checkpoint_files(directory):
    return sorted(directory.glob("checkpoint-*.json"),
                  key=lambda path: int(path.stem.removeprefix("checkpoint-")))


def read_checkpoint(path):
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != 1:
        raise ValueError(f"Unsupported checkpoint format: {path}")
    return checkpoint


def save_checkpoint(directory, checkpoint):
    """Publish a complete checkpoint without overwriting one from another process."""
    destination = directory / f"checkpoint-{checkpoint['generation']:04d}.json"
    file = NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False)
    temporary = Path(file.name)
    try:
        with file:
            json.dump(checkpoint, file, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            file.write("\n")
        os.link(temporary, destination)
    finally:
        temporary.unlink()
    return destination


@contextlib.contextmanager
def training_lock(directory):
    """Prevent competing writers to a run. The OS releases the lock on process exit."""
    with (directory / ".training.lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt

                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f"Could not lock {directory}. Check for another active trainer.") from exc
        yield


def model_from_record(record):
    return None if record["weights"] is None else LinearEvaluator(tuple(record["weights"]))


def print_score(label, evaluation):
    row = evaluation["overall"]
    print(f"{label}: {row['points']}/{2 * row['games']} points "
          f"(W {row['wins']} D {row['draws']} L {row['losses']})", flush=True)


def optimization_candidates(fitted, incumbent, rng, generation):
    """Try a data-driven update and a perturbation of the strongest tested weights."""
    if incumbent is None:
        # Convert the hand-tuned defender score to the scaled feature representation.
        weights = (-4 * DEFENDER_WEIGHTS["king_safety"], 4 * DEFENDER_WEIGHTS["escape_routes"],
                   -16 * DEFENDER_WEIGHTS["piece_advantage"], 0.0)
        scale = max(1.0, sum(map(abs, weights)))
        anchor = tuple(weight / scale for weight in weights)
    else:
        anchor = incumbent.weights
    fraction = (0.15, 0.35, 0.60, 1.0)[generation % 4]
    blended = tuple(before + fraction * (after - before) for before, after in zip(anchor, fitted.weights))
    radius = (0.08, 0.16, 0.32)[generation % 3]
    perturbed = tuple(weight + rng.uniform(-radius, radius) for weight in anchor)
    return (("blend", LinearEvaluator(blended)), ("perturbation", LinearEvaluator(perturbed)))


def points(record):
    return record["evaluation"]["overall"]["points"]


def train_iteration(checkpoint, history, *, optimize=False):
    config = checkpoint["config"]
    generation = checkpoint["generation"] + 1
    rng = Random(f"{config['seed']}:training:{generation}")
    current = model_from_record(checkpoint["candidate"])
    best = checkpoint["best"]
    incumbent = model_from_record(best)
    older = [None, incumbent] + history
    samples, outcomes = [], Counter()
    for index in range(config["train_games"]):
        evaluators = {"A": current, "D": current}
        if index % 4 >= 2:
            evaluators["A" if index % 2 == 0 else "D"] = rng.choice(older)
        result, rows = play_training_game(evaluators, rng, config["max_plies"])
        outcomes[result] += 1
        samples.extend(rows)
    if not samples:
        raise ValueError("No completed training games. Resume with a larger --max-plies.")

    batches = (checkpoint["replay_batches"] + [samples])[-REPLAY_ITERATIONS:]
    fitted = fit_evaluator([row for batch in batches for row in batch])
    print(f"Iteration {generation}: {len(samples)} positions from "
          f"{config['train_games'] - outcomes['truncated']} completed games; "
          f"{outcomes['truncated']} truncated", flush=True)
    models = (("ridge", fitted),)
    if optimize:
        search_rng = Random(f"{config['seed']}:optimization:{generation}")
        models = optimization_candidates(fitted, incumbent, search_rng, generation)
    trials = []
    for method, model in models:
        evaluation = evaluate(model, config)
        trials.append(dict(generation=generation, method=method, weights=model.weights, evaluation=evaluation))
        if optimize:
            print_score(method, evaluation)
    candidate = max(trials, key=points)
    if points(candidate) > points(best):
        best = candidate
    return dict(schema_version=1, generation=generation, config=config, candidate=candidate,
                best=best, replay_batches=batches, training_outcomes=dict(outcomes), trials=trials)


def run_training(parser, args, config, explicit):
    paths = checkpoint_files(args.output_dir)
    history = []
    if args.resume:
        if not paths:
            parser.error("No training checkpoint to resume")
        checkpoint = read_checkpoint(paths[-1])
        for key in ("seed", "eval_pairs"):
            if key in explicit and checkpoint["config"][key] != explicit[key]:
                parser.error(f"--{key.replace('_', '-')} changes the evaluation suite")
        for key in ("train_games", "max_plies"):
            if key in explicit:
                checkpoint["config"][key] = explicit[key]
        history = [model_from_record(read_checkpoint(path)["candidate"])
                   for path in paths[-HISTORICAL_MODELS - 1:-1]]
    else:
        if paths:
            parser.error("Checkpoints already exist. Use --resume or choose a new directory.")
        baseline = dict(generation=0, weights=None, evaluation=evaluate(None, config))
        print_score("Hand-tuned baseline", baseline["evaluation"])
        checkpoint = dict(schema_version=1, generation=0, config=config, candidate=baseline,
                          best=baseline, replay_batches=[], training_outcomes={})
        save_checkpoint(args.output_dir, checkpoint)

    stop_file = args.output_dir / STOP_FILE
    if args.continuous:
        print(f"Continuous optimization on PID {os.getpid()} from iteration "
              f"{checkpoint['generation']}; stop file: {stop_file.resolve()}", flush=True)
    for _ in count() if args.continuous else range(args.iterations):
        if args.continuous and stop_file.exists():
            print(f"Stop requested. Last completed iteration: {checkpoint['generation']}", flush=True)
            break
        previous = checkpoint["candidate"]
        checkpoint = train_iteration(checkpoint, history, optimize=args.continuous)
        saved = save_checkpoint(args.output_dir, checkpoint)
        history = (history + [model_from_record(previous)])[-HISTORICAL_MODELS:]
        print_score("Candidate", checkpoint["candidate"]["evaluation"])
        print_score(f"Best iteration {checkpoint['best']['generation']}", checkpoint["best"]["evaluation"])
        print(f"Checkpoint: {saved.resolve()}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument("--iterations", type=int, default=1, help="Number of additional iterations")
    duration.add_argument("--continuous", action="store_true",
                          help="Optimize until a STOP file appears in the run directory")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "training" / "default")
    parser.add_argument("--resume", action="store_true", help="Continue from the latest checkpoint")
    parser.add_argument("--seed", type=int, help="Seed for independent training and evaluation streams")
    parser.add_argument("--train-games", type=int, help="Self-play games per iteration")
    parser.add_argument("--eval-pairs", type=int, help="Paired openings per fixed opponent")
    parser.add_argument("--max-plies", type=int, help="Training-only plies cap; truncated games are discarded")
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    explicit = {key: getattr(args, key) for key in DEFAULTS if getattr(args, key) is not None}
    config = dict(DEFAULTS, **explicit)
    if min(config["train_games"], config["eval_pairs"], config["max_plies"]) < 1:
        parser.error("Game count, evaluation pairs and ply cap must be positive")
    if args.resume and not args.output_dir.is_dir():
        parser.error("No training checkpoint to resume")
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        with training_lock(args.output_dir):
            run_training(parser, args, config, explicit)
    except KeyboardInterrupt:
        parser.exit(130, "Training interrupted. Resume from the last completed checkpoint.\n")
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        parser.exit(1, f"Training stopped: {exc}\n")


if __name__ == "__main__":
    main()
