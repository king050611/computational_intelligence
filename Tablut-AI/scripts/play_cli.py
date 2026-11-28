"""Local Human vs AI play using the official referee; human input is untimed."""
import argparse
import copy
import re
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "reference")]
from Tablut import Tablut, TIME_BUDGET
from src.experimental_player import ExperimentalPlayer
from src.evaluation import load_evaluator
from src.game import get_legal_moves
from config.experimental import AVAILABLE_STRATEGIES as STRATEGIES

COLUMNS = "ABCDEFGHI"
HELP = """Enter a move as FROM TO, for example: D1 C1.
Columns: A-I; rows: 1-9. A1 is the top-left square.
help  - show this help
moves - list all legal moves for your side
board - display the board again
quit  - abort the game without declaring a winner
Pieces: A=attacker, D=defender, K=king, X=empty castle, .=empty.
All pieces slide horizontally or vertically without jumping.
An empty castle may be crossed, but cannot be a destination."""


def parse_square(text):
    """Convert A1-I9 (case insensitive) to zero-based (row, column)."""
    if re.fullmatch(r"[A-Ia-i][1-9]", text) is None:
        raise ValueError("Use a square from A1 to I9.")
    return int(text[1]) - 1, COLUMNS.index(text[0].upper())


def parse_move(text):
    squares = text.split()
    if len(squares) != 2:
        raise ValueError("Enter two squares, for example: D1 C1.")
    return tuple(parse_square(square) for square in squares)


def format_square(square):
    row, column = square
    return f"{COLUMNS[column]}{row + 1}"


def format_move(move):
    return " ".join(format_square(square) for square in move)


def display_board(board, write=print):
    write("\n    " + " ".join(COLUMNS))
    for row, cells in enumerate(board, 1):
        write(f"{row:>2}  " + " ".join(cells))
    write("")


def read_human_move(board, side, *, input_fn=input, write=print):
    """Return a legal internal Move, or None for quit; never mutate the game."""
    legal_moves = get_legal_moves(board, side)
    while True:
        text = input_fn(f"Human {side}> ").strip()
        command = text.lower()
        if command == "quit":
            return None
        if command == "help":
            write(HELP)
            continue
        if command == "board":
            display_board(board, write)
            continue
        if command == "moves":
            write(f"Legal moves for {side}: {len(legal_moves)}")
            for start in range(0, len(legal_moves), 6):
                write(" | ".join(format_move(move) for move in legal_moves[start:start + 6]))
            continue
        try:
            move = parse_move(text)
        except ValueError as exc:
            write(f"Invalid input: {exc}")
            continue
        if move not in legal_moves:
            write("Illegal move. Check your piece, destination, and clear orthogonal path.")
            continue
        return move


def display_search_stats(stats, write=print):
    if not stats:
        write("Search: not recorded.")
        return
    def value(key):
        result = stats.get(key)
        return "unrecorded" if result is None else str(result)
    write("Search: " + "; ".join(
        f"{key}={value(key)}" for key in
        ("strategy", "target_depth", "completed_depth", "nodes",
         "policy_reason", "finish_reason", "timed_out", "fallback_used")))


def run_game(human_side, strategy="enhanced_dynamic", seed=42, show_search=False, *,
             input_fn=input, write=print, game=None, ai=None, evaluator=None, recording=None):
    """Run one local game. Return its outcome; do not save a replay in this phase."""
    if human_side not in ("A", "D"):
        raise ValueError("Human side must be A or D.")
    if strategy not in STRATEGIES:
        raise ValueError("Unknown AI strategy.")
    game = Tablut() if game is None else game
    if ai is None:
        ai = ExperimentalPlayer(strategy, seed=seed, record_search=show_search, evaluator=evaluator, opening=game.board)
    ai_seconds = 0.0

    def finish(status, winner, reason):
        game.winner = winner if status == "finished" and winner in ("A", "D") else None
        if status == "aborted":
            write(f"Game aborted ({reason}); no winner.")
        elif status == "error":
            write(f"Game stopped ({reason}); no winner.")
        elif winner == "DRAW":
            write("Result: DRAW (official referee).")
        else:
            who = "Human" if winner == human_side else "AI"
            write(f"Result: {who} wins ({winner}); {reason}.")
        write(f"Referee move count: {game.rounds_played}; AI time: {ai_seconds:.3f}/{TIME_BUDGET:.0f}s")
        result = dict(status=status, winner=winner, reason=reason,
                      plies=game.rounds_played, ai_seconds=ai_seconds)
        if recording is not None:
            recording.update(result=result, final_board=copy.deepcopy(game.board))
        return result

    write("Tablut - Human vs AI")
    write(f"Human: {human_side}; AI: {'D' if human_side == 'A' else 'A'} ({strategy}).")
    write(f"Human input has no time limit; AI has {TIME_BUDGET:.0f}s total. Type help for commands.")
    display_board(game.board, write)
    # Initial check seeds the same turn-aware history as official play(), while
    # also handling an already-terminal board supplied by a test or local tool.
    game.past_positions = []
    if game.check_if_game_over(True):
        return finish("finished", game.winner or "DRAW", "game_over")
    if recording is not None:
        recording.update(initial_board=copy.deepcopy(game.board), moves=[])
    current_side = "A"
    try:
        while True:
            is_human = current_side == human_side
            if is_human:
                move = read_human_move(game.board, current_side, input_fn=input_fn, write=write)
                if move is None:
                    return finish("aborted", None, "quit")
            else:
                write(f"AI ({current_side}) is thinking...")
                ai_board = copy.deepcopy(game.board)
                started = perf_counter()
                try:
                    try:
                        play = ai.play_attacker if current_side == "A" else ai.play_defender
                        move = play(ai_board)
                    finally:
                        elapsed = perf_counter() - started
                        ai_seconds += elapsed
                except Exception as exc:
                    write(f"AI error: {type(exc).__name__}: {exc}")
                    return finish("finished", human_side, "ai_exception")
                if ai_seconds > TIME_BUDGET:
                    write("AI exceeded its cumulative time limit.")
                    return finish("finished", human_side, "ai_timeout")
                valid_shape = (isinstance(move, (list, tuple)) and len(move) == 2
                               and all(isinstance(pos, (list, tuple)) and len(pos) == 2
                                       and all(type(n) is int for n in pos) for pos in move))
                if not valid_shape:
                    write(f"AI returned a malformed move: {move!r}")
                    return finish("finished", human_side, "ai_illegal_move")
                move = tuple(tuple(pos) for pos in move)
                if move not in get_legal_moves(game.board, current_side):
                    write(f"AI returned an illegal move: {move!r}")
                    return finish("finished", human_side, "ai_illegal_move")
                write(f"AI {current_side}: {format_move(move)}; {elapsed:.3f}s; total {ai_seconds:.3f}s")
                if show_search:
                    display_search_stats(getattr(ai, "last_search_stats", None), write)
            # Invalid human input never reaches the official make_move counter.
            before = copy.deepcopy(game.board) if recording is not None else None
            if not game.make_move(current_side == "A", move):
                write("Referee rejected a prevalidated move; game stopped for inspection.")
                return finish("error", None, "referee_rejected_move")
            if recording is not None:
                recording["moves"].append(dict(player=current_side, move=move, accepted=True,
                    board_before=before, board_after=copy.deepcopy(game.board),
                    elapsed_seconds=0 if is_human else elapsed,
                    search=None if is_human else getattr(ai,"last_search_stats",None)))
            if is_human:
                write(f"Human {current_side}: {format_move(move)}")
            display_board(game.board, write)
            current_side = "D" if current_side == "A" else "A"
            if game.check_if_game_over(current_side == "A"):
                return finish("finished", game.winner or "DRAW", "game_over")
    except EOFError:
        return finish("aborted", None, "eof")
    except KeyboardInterrupt:
        return finish("aborted", None, "interrupted")


def main(argv=None, *, independent=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", type=str.upper, choices=("A", "D"), help="Your side; prompts if omitted.")
    parser.add_argument("--strategy", choices=STRATEGIES, default="enhanced_dynamic")
    parser.add_argument("--seed", type=int, default=42, help="Seed for the random strategy.")
    parser.add_argument("--show-search", action="store_true", help="Show recorded AI search statistics.")
    parser.add_argument("--model", type=Path, help="Required only with evolutionary_dynamic")
    if independent:
        parser.add_argument("--output", type=Path, help="Save a JSON game record")
    args = parser.parse_args(argv)
    if (args.strategy == "evolutionary_dynamic") != (args.model is not None):
        parser.error("--model is required only for evolutionary_dynamic")
    try:
        evaluator = load_evaluator(args.model) if args.model else None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    side = args.side
    try:
        while side is None:
            choice = input("Choose your side [A=attacker, D=defender, quit]: ").strip().upper()
            if choice == "QUIT":
                print("Game aborted (quit); no winner.")
                return 0
            if choice in ("A", "D"):
                side = choice
            else:
                print("Please choose A or D, or type quit.")
    except (EOFError, KeyboardInterrupt):
        print("Game aborted before side selection; no winner.")
        return 0
    if independent:
        from src.role_player import RolePlayer
        import json
        recording = dict(human_side=side) if args.output else None
        if args.output and args.output.exists():
            parser.error("Replay output already exists")
        with RolePlayer(record_search=args.show_search) as player:
            ai = player if args.strategy == "enhanced_dynamic" and not args.model else None
            result = run_game(side, args.strategy, args.seed, args.show_search, input_fn=input,
                              evaluator=evaluator, ai=ai, recording=recording)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x",encoding="utf-8") as file:
                json.dump(recording,file,indent=2)
    else:
        result = run_game(side, args.strategy, args.seed, args.show_search, input_fn=input, evaluator=evaluator)
    return int(result["status"] == "error" or result["reason"].startswith("ai_"))


if __name__ == "__main__":
    raise SystemExit(main())
