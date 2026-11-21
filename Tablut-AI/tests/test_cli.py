"""Human CLI input and official-referee integration, using deterministic fake AI."""
import copy
import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from scripts import play_cli as cli


def sparse_game(pieces):
    game = cli.Tablut()
    game.board = [["."] * 9 for _ in range(9)]
    game.board[4][4] = "X"
    for (row, column), piece in pieces.items():
        game.board[row][column] = piece
    return game


def inputs(*commands):
    commands = iter(commands)
    return lambda prompt: next(commands)


class CLIInputTests(unittest.TestCase):
    def test_square_and_move_coordinates(self):
        for square, position in (("A1", (0, 0)), ("i9", (8, 8)), ("D1", (0, 3))):
            with self.subTest(square=square):
                self.assertEqual(cli.parse_square(square), position)
                self.assertEqual(cli.format_square(position), square.upper())
        move = ((0, 3), (0, 2))
        self.assertEqual(cli.parse_move("  d1   c1  "), move)
        self.assertEqual(cli.format_move(move), "D1 C1")

    def test_invalid_coordinates_and_move_shapes(self):
        for square in ("A0", "A10", "J1", "1A", "AA1", "", "A-1"):
            with self.subTest(square=square), self.assertRaises(ValueError):
                cli.parse_square(square)
        for text in ("", "A1", "A1 A2 A3", "A1 J2", "A1,A2"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                cli.parse_move(text)

    def test_board_displays_full_ascii_grid(self):
        output = []
        cli.display_board(cli.Tablut().board, write=output.append)
        text = "\n".join(output)
        for column in "ABCDEFGHI":
            self.assertIn(column, text)
        for row in range(1, 10):
            self.assertIn(str(row), text)
        self.assertIn("K", text)
        self.assertIn(".", text)
        self.assertTrue(text.isascii())

    def test_commands_and_invalid_moves_do_not_touch_game(self):
        game = cli.Tablut()
        before = copy.deepcopy(game.board)
        output = []
        # Wrong side, occupied target, diagonal, blocked path, outside board.
        move = cli.read_human_move(
            game.board, "A", write=output.append,
            input_fn=inputs("HELP", "BOARD", "MOVES", "E5 E4", "D1 E1",
                            "D1 E2", "D1 D9", "J1 A1", "D1 C1"),
        )
        self.assertEqual(move, ((0, 3), (0, 2)))
        self.assertEqual(game.board, before)
        self.assertEqual(game.rounds_played, 0)
        self.assertTrue(output)

    def test_quit_and_input_interrupts(self):
        self.assertIsNone(cli.read_human_move(cli.Tablut().board, "A", input_fn=inputs("QUIT"), write=lambda text: None))
        for error in (EOFError, KeyboardInterrupt):
            with self.subTest(error=error), self.assertRaises(error):
                cli.read_human_move(cli.Tablut().board, "A", input_fn=Mock(side_effect=error), write=lambda text: None)


class CLIGameTests(unittest.TestCase):
    def run_quiet(self, side, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return cli.run_game(side, write=lambda text: None, **kwargs)

    def test_defender_selection_gives_ai_first_move_and_a_copy(self):
        game = cli.Tablut()
        initial_hash = game.compute_zobrist_hash(True)

        def ai_move(board):
            self.assertEqual(game.past_positions, [initial_hash])
            self.assertIsNot(board, game.board)
            board[8][8] = "D"
            return [[0, 3], [0, 2]]

        bot = Mock()
        bot.play_attacker.side_effect = ai_move

        def human_input(prompt):
            self.assertEqual(game.rounds_played, 1)
            self.assertEqual(game.board[0][2], "A")
            self.assertEqual(game.board[8][8], ".")
            return "quit"

        result = self.run_quiet("D", game=game, ai=bot, input_fn=human_input)
        self.assertEqual(result["status"], "aborted")
        self.assertIsNone(result["winner"])
        bot.play_attacker.assert_called_once()
        bot.play_defender.assert_not_called()

    def test_human_attacker_capture_ends_before_ai_turn(self):
        game = sparse_game({(2, 2): "K", (2, 1): "A", (2, 6): "A"})
        bot = Mock()
        result = self.run_quiet("A", game=game, ai=bot, input_fn=inputs("G3 D3"))
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["winner"], "A")
        self.assertEqual(game.rounds_played, 1)
        bot.play_defender.assert_not_called()

    def test_human_defender_escape_after_ai_opening(self):
        game = sparse_game({(1, 2): "K", (8, 8): "A", (8, 6): "A"})
        bot = Mock()
        bot.play_attacker.return_value = [[8, 8], [7, 8]]
        result = self.run_quiet("D", game=game, ai=bot, input_fn=inputs("C2 C1"))
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["winner"], "D")
        self.assertEqual(game.board[0][2], "K")
        self.assertEqual(game.rounds_played, 2)

    def test_ai_capture_and_escape_are_real_wins(self):
        cases = [
            ("D", {(2, 2): "K", (2, 1): "A", (2, 6): "A"},
             "play_attacker", [[2, 6], [2, 3]], (), "A"),
            ("A", {(1, 2): "K", (8, 8): "A", (8, 6): "A"},
             "play_defender", [[1, 2], [0, 2]], ("I9 I8",), "D"),
        ]
        for side, pieces, method, move, commands, winner in cases:
            with self.subTest(side=side):
                bot = Mock()
                getattr(bot, method).return_value = move
                result = self.run_quiet(side, game=sparse_game(pieces), ai=bot, input_fn=inputs(*commands))
                self.assertEqual((result["status"], result["winner"]), ("finished", winner))

    def test_repetition_draw_includes_initial_position(self):
        game = cli.Tablut()
        bot = Mock()
        bot.play_defender.side_effect = [[[2, 4], [2, 3]], [[2, 3], [2, 4]]]
        result = self.run_quiet("A", game=game, ai=bot, input_fn=inputs("D1 C1", "C1 D1"))
        self.assertEqual((result["status"], result["winner"]), ("finished", "DRAW"))
        self.assertEqual(game.rounds_played, 4)
        self.assertIn(game.compute_zobrist_hash(True), game.past_positions)

    def test_no_legal_moves_is_official_draw(self):
        game = cli.Tablut()
        game.board = [["A"] * 9 for _ in range(9)]
        game.board[4][4] = "K"
        game.board[0][2] = "."
        result = self.run_quiet("A", game=game, ai=Mock(), input_fn=inputs("B1 C1"))
        self.assertEqual((result["status"], result["winner"]), ("finished", "DRAW"))
        self.assertEqual(game.rounds_played, 1)

    def test_quit_eof_and_interrupt_are_aborted_not_drawn(self):
        for input_fn, reason in ((inputs("quit"), "quit"),
                                 (Mock(side_effect=EOFError), "eof"),
                                 (Mock(side_effect=KeyboardInterrupt), "interrupted")):
            with self.subTest(reason=reason):
                game, bot = cli.Tablut(), Mock()
                with patch.object(cli, "perf_counter", side_effect=AssertionError("Human turn was timed")):
                    result = self.run_quiet("A", game=game, ai=bot, input_fn=input_fn)
                self.assertEqual(result["status"], "aborted")
                self.assertEqual(result["reason"], reason)
                self.assertIsNone(result["winner"])
                self.assertEqual(game.rounds_played, 0)
                bot.play_defender.assert_not_called()

    def test_ai_exception_and_illegal_output_are_forfeits(self):
        for value, reason in ((RuntimeError("test failure"), "ai_exception"),
                              (None, "ai_illegal_move"),
                              ([[0, 3], [0, 4]], "ai_illegal_move")):
            with self.subTest(reason=reason, value=value):
                bot, game = Mock(), cli.Tablut()
                if isinstance(value, Exception):
                    bot.play_attacker.side_effect = value
                else:
                    bot.play_attacker.return_value = value
                result = self.run_quiet("D", game=game, ai=bot, input_fn=inputs())
                self.assertEqual((result["status"], result["winner"], result["reason"]),
                                 ("finished", "D", reason))
                self.assertEqual(game.rounds_played, 0)

    def test_ai_budget_is_checked_before_applying_move(self):
        game, bot = cli.Tablut(), Mock()
        bot.play_attacker.return_value = [[0, 3], [0, 2]]
        with patch.object(cli, "perf_counter", side_effect=[0.0, 61.0]):
            result = self.run_quiet("D", game=game, ai=bot, input_fn=inputs())
        self.assertEqual((result["winner"], result["reason"]), ("D", "ai_timeout"))
        self.assertEqual(game.rounds_played, 0)

    def test_ai_budget_accumulates_across_turns(self):
        game, bot = cli.Tablut(), Mock()
        clock = [0.0]
        moves = iter(([[0, 3], [0, 2]], [[0, 2], [0, 1]]))

        def ai_move(board):
            clock[0] += 31.0
            return next(moves)

        bot.play_attacker.side_effect = ai_move
        with patch.object(cli, "perf_counter", side_effect=lambda: clock[0]):
            result = self.run_quiet("D", game=game, ai=bot, input_fn=inputs("E3 D3"))
        self.assertEqual((result["winner"], result["reason"]), ("D", "ai_timeout"))
        self.assertEqual(result["ai_seconds"], 62.0)
        self.assertEqual(game.rounds_played, 2)
        self.assertEqual(game.board[0][2], "A")
        self.assertEqual(game.board[0][1], ".")

    def test_show_search_reports_actual_values_and_missing_data(self):
        bot = Mock()
        bot.play_attacker.return_value = [[0, 3], [0, 2]]
        bot.last_search_stats = dict(strategy="adaptive", target_depth=3,
                                     completed_depth=2, nodes=123,
                                     timed_out=True, fallback_used=True)
        output = []
        with contextlib.redirect_stdout(io.StringIO()):
            result = cli.run_game("D", ai=bot, show_search=True,
                                  input_fn=inputs("quit"), write=output.append)
        self.assertEqual(result["status"], "aborted")
        text = "\n".join(output)
        for value in ("target_depth=3", "completed_depth=2", "nodes=123", "fallback_used=True"):
            self.assertIn(value, text)
        output = []
        cli.display_search_stats(None, write=output.append)
        self.assertIn("not recorded", "\n".join(output).lower())


class CLIEntryTests(unittest.TestCase):
    def test_side_prompt_retries_and_cli_options_reach_controller(self):
        with patch("builtins.input", side_effect=("wrong", "d")), \
             patch.object(cli, "run_game", return_value=dict(status="aborted", winner=None, reason="quit")) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["--strategy", "random", "--seed", "100", "--show-search"]), 0)
        self.assertEqual(run.call_args.args, ("D", "random", 100, True))

    def test_ai_failure_has_nonzero_exit_while_quit_is_successful(self):
        for status, reason, expected in (("finished", "ai_exception", 1),
                                         ("error", "referee_rejected_move", 1),
                                         ("aborted", "quit", 0)):
            with self.subTest(reason=reason), \
                 patch.object(cli, "run_game", return_value=dict(status=status, reason=reason)):
                self.assertEqual(cli.main(["--side", "A"]), expected)


if __name__ == "__main__":
    unittest.main()
