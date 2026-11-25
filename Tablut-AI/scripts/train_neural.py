"""Train value + Alpha–Beta first, then policy and value + MCTS on CPU."""
import argparse
from collections import Counter
from contextlib import redirect_stdout
import io
from itertools import count
import json
import os
from pathlib import Path
from random import Random
import re
import sys

# Small single-position matrix operations are faster without BLAS thread fan-out.
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(variable, "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "reference")]

import numpy as np

from Tablut import Tablut
from scripts.benchmark import StrategyBot, Timed, standings
from scripts.train_selfplay import opening_board, training_lock
from src.game import apply_move, check_winner, get_legal_moves, get_state_key, initial_board
from src.learning import load_evaluator
from src.neural import Network, OUTCOME_VALUE, Sample, load_network, save_network
from src.neural_player import NeuralPlayer, monte_carlo_search, other_side
from src.search import choose_move


DEFAULTS = dict(seed=6421, value_rounds=1, train_games=12, eval_pairs=3,
                simulations=16, epochs=3, max_plies=120)


def checkpoints(directory):
    entries = ((int(match[1]), path) for path in directory.iterdir()
               if (match := re.fullmatch(r"checkpoint-(\d+)\.npz", path.name)))
    return dict(sorted(entries))


def make_openings(seed, pairs):
    boards, seen = [], set()
    for index in count():
        board = opening_board(f"{seed}:neural-arena", index)
        if board not in seen:
            boards.append(board)
            seen.add(board)
        if len(boards) == pairs * 2:
            return boards[:pairs], boards[pairs:]


def arena(make_ours, make_opponent, openings):
    """Swap roles from every opening, using the official referee and its clock."""
    results = []
    for number, board in enumerate(openings, 1):
        for side in ("A", "D"):
            ours = Timed(make_ours(board))
            opponent = Timed(make_opponent(board))
            attacker, defender = (ours, opponent) if side == "A" else (opponent, ours)
            game = Tablut()
            game.board = [list(row) for row in board]
            with redirect_stdout(io.StringIO()) as log:
                game.play(attacker, defender)
            message = log.getvalue()
            if (attacker.errors or defender.errors or attacker.invalid_returns or defender.invalid_returns
                    or "exceeded time limit" in message or "Illegal move" in message):
                raise RuntimeError(f"Neural evaluation failed at opening {number}, role {side}: {message}")
            results.append({"opening": number, "our_side": side, "winner": game.winner or "DRAW",
                            "plies": game.rounds_played, "our_seconds": sum(ours.times)})
    return {**standings(results), "games": results}


def collect_game(actors, config, rng, search_rng):
    board, side = initial_board(), "A"
    history, positions = [], []
    for ply in range(config["max_plies"] + 1):
        winner = check_winner(board, side, history)
        if winner:
            return winner, [Sample(*position, OUTCOME_VALUE[winner], policy)
                            for position, policy in positions]
        if ply == config["max_plies"]:
            break
        phase, model = actors[side]
        policy = ()
        if phase == "policy":
            move, policy = monte_carlo_search(
                model, board, side, config["simulations"], history=history,
                noise=search_rng, sample_move=ply < 6,
            )
        elif ply < 6 or rng.random() < 0.10:
            move = rng.choice(get_legal_moves(board, side))
        else:
            move = choose_move(board, side, strategy="minimax", history=history,
                               evaluator=model if phase == "linear" else None,
                               position_value=model.value if phase == "value" else None)
        positions.append(((board, side), policy))
        history.append(get_state_key(board, side))
        board, side = apply_move(board, move, side), other_side(side)
    return "truncated", []


def collect_batch(network, phase, number, config, reference, historical):
    rng = Random(f"{config['seed']}:neural-data:{number}")
    search_rng = np.random.default_rng(rng.getrandbits(64))
    active = ("linear", reference) if number == 1 else (phase, network)
    games, data = Counter(), []
    for game in range(config["train_games"]):
        actors = {"A": active, "D": active}
        if game % 4 >= 2:
            actors["A" if game % 2 == 0 else "D"] = rng.choice(historical)
        outcome, samples = collect_game(actors, config, rng, search_rng)
        games[outcome] += 1
        data.extend(sample for sample in samples if phase == "value" or sample.policy)
    if not data:
        raise ValueError("No completed games yielded training samples")
    return data, games


def describe(label, stats):
    score = stats["overall"]
    print(f"{label}: {score['points']}/{2 * score['games']} "
          f"(W {score['wins']} D {score['draws']} L {score['losses']})", flush=True)


def train(args):
    directory = args.output_dir
    if args.resume and not directory.is_dir():
        raise ValueError("No neural run to resume")
    directory.mkdir(parents=True, exist_ok=True)
    with training_lock(directory):
        files = checkpoints(directory)
        overrides = {key: getattr(args, key) for key in DEFAULTS if getattr(args, key) is not None}
        if args.resume:
            if not files:
                raise ValueError("No neural checkpoint to resume")
            number = max(files)
            network, previous = load_network(files[number])
            config, best = previous["config"], previous["best"]
            if overrides or args.reference is not None:
                raise ValueError("Resume uses the configuration saved in the checkpoint")
            reference_path = previous["reference"]
        else:
            if files:
                raise ValueError("Neural checkpoints exist. Use --resume or choose another directory.")
            number, best = 0, {}
            config = dict(DEFAULTS, **overrides)
            network = Network.initialize(config["seed"])
            reference_path = str(args.reference.resolve()) if args.reference else None
        if min(config[key] for key in DEFAULTS if key != "seed") < 1 or config["seed"] < 0:
            raise ValueError("Training settings must be positive and the seed nonnegative")
        reference = load_evaluator(reference_path) if reference_path else None
        selection, holdout = make_openings(config["seed"], config["eval_pairs"])
        reference_name = "trained three-feature model" if reference is not None else "hand-tuned three-feature model"
        print(f"Neural training PID {os.getpid()} from checkpoint {number}; reference: {reference_name}; "
              f"stop file: {directory / 'STOP'}", flush=True)

        def linear_opponent(board):
            return StrategyBot("minimax", config["seed"], evaluator=reference)

        final = config["value_rounds"] + 1
        for iteration in count(number + 1) if args.continuous else range(number + 1, max(final, number + 1) + 1):
            if (directory / "STOP").exists():
                print(f"Stop requested. Last completed neural checkpoint: {iteration - 1}", flush=True)
                break
            phase = "value" if iteration <= config["value_rounds"] else "policy"
            first_in_phase = phase not in best
            historical = [("linear", reference)]
            if phase == "policy":
                value_net, _ = load_network(files[best["value"]["iteration"]])
                historical.append(("value", value_net))
                if first_in_phase:
                    network, _ = load_network(files[best["value"]["iteration"]])
                else:
                    past_policy, _ = load_network(files[best["policy"]["iteration"]])
                    historical.append(("policy", past_policy))
                latest_policy = [index for index in files if index > config["value_rounds"]]
                if len(latest_policy) > 1:
                    earlier, _ = load_network(files[latest_policy[-2]])
                    historical.append(("policy", earlier))
            print(f"Iteration {iteration} [{phase}]: playing {config['train_games']} training games", flush=True)
            samples, games = collect_batch(network, phase, iteration, config, reference, historical)
            loss = network.fit(samples, epochs=config["epochs"],
                               rng=np.random.default_rng([config["seed"], iteration]),
                               learn_policy=phase == "policy")
            print(f"Iteration {iteration}: fit {len(samples)} positions; {games.get('truncated', 0)} games truncated; "
                  f"loss={json.dumps(loss)}", flush=True)

            def neural_player(board):
                return NeuralPlayer(network, phase, config["simulations"], board)

            selected = arena(neural_player, linear_opponent, selection)
            describe(f"{phase} vs three-feature model (selection)", selected)
            evaluation = {"selection": selected}
            if first_in_phase:
                evaluation["holdout"] = arena(neural_player, linear_opponent, holdout)
                describe(f"{phase} vs three-feature model (unseen evaluation openings)", evaluation["holdout"])
                if phase == "policy":
                    evaluation["versus_value"] = arena(
                        neural_player, lambda board: NeuralPlayer(value_net, "value", config["simulations"], board),
                        holdout,
                    )
                    describe("policy + MCTS vs value + Alpha–Beta", evaluation["versus_value"])
            points = selected["overall"]["points"]
            if first_in_phase or points > best[phase]["points"]:
                best[phase] = {"iteration": iteration, "points": points}
            path = directory / f"checkpoint-{iteration:04d}.npz"
            save_network(path, network, {
                "schema_version": 1, "iteration": iteration, "phase": phase, "config": config,
                "best": best, "reference": reference_path, "training_games": dict(games),
                "samples": len(samples), "loss": loss, "evaluation": evaluation,
            })
            files[iteration] = path
            print(f"Checkpoint: {path.resolve()}; best {phase}: {best[phase]}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "training" / "neural")
    parser.add_argument("--reference", type=Path, help="Linear-training JSON checkpoint for the benchmark and teacher")
    parser.add_argument("--resume", action="store_true", help="Resume this neural run")
    parser.add_argument("--continuous", action="store_true", help="Continue MCTS training until a STOP file appears")
    for key, default in DEFAULTS.items():
        parser.add_argument("--" + key.replace("_", "-"), type=int, help=f"New run default: {default}")
    args = parser.parse_args()
    try:
        train(args)
    except KeyboardInterrupt:
        parser.exit(130, "Neural training interrupted. Resume from the latest completed checkpoint.\n")
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        parser.exit(1, f"Neural training stopped: {exc}\n")


if __name__ == "__main__":
    main()
