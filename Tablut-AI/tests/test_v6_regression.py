"""V6 regressions for history-sensitive scores and draw decisions."""
import json
from math import inf
from pathlib import Path
from random import Random
import unittest

from config.experimental import SearchOptions
from src.enhanced_search import EnhancedSearch, choose_enhanced, reply_repetitions
from src.features import immediate_king_threat, king_escape_distance
from src.game import apply_move, check_winner, get_legal_moves, get_state_key, initial_board


class DrawDecisions(unittest.TestCase):
    def test_keeps_a_draw_when_the_alternative_scores_below_it(self):
        board = initial_board()
        repeating, other = get_legal_moves(board, "A")[:2]
        history = (get_state_key(apply_move(board, repeating, "A"), "D"),)
        move = choose_enhanced(board, "A", deadline=inf, history=history, moves=[other, repeating],
                               evaluator=lambda *_: -50, options=SearchOptions(1, draw_policy=True))
        self.assertEqual(move, repeating)

    def test_advantage_prefers_equal_line_without_verified_repeat_reply(self):
        board = initial_board()
        risk, safe = get_legal_moves(board, "A")[:2]
        child = apply_move(board, risk, "A")
        reply = get_legal_moves(child, "D")[0]
        repeated = apply_move(child, reply, "D")
        history = (get_state_key(repeated, "A"),)
        stats = {}
        move = choose_enhanced(board, "A", deadline=inf, stats=stats, history=history, moves=[risk, safe],
                               evaluator=lambda position, _: 50 if position == board else 0,
                               options=SearchOptions(2, draw_policy=True))
        self.assertEqual(stats["reply_draw_moves"], 1)
        self.assertEqual(stats["score"], 0)
        self.assertEqual(move, safe)

    def test_repeat_reply_inference_requires_a_real_legal_move(self):
        board = initial_board()
        move = get_legal_moves(board, "A")[0]
        child = apply_move(board, move, "A")
        targets = {(apply_move(child, reply, "D"), "A") for reply in get_legal_moves(child, "D")}
        self.assertEqual(reply_repetitions({move: child}, "D", targets, inf, apply_move, set()), ({move}, True))
        self.assertEqual(reply_repetitions({move: child}, "D", targets, 0, apply_move, set()), (set(), False))

    def test_repeated_end_from_historical_greedy_replay_is_still_available(self):
        source = Path(__file__).resolve().parents[1] / "reports/replays/depth_greedy/games.json"
        games = json.loads(source.read_bytes())["games"]
        game = next(item for item in games if item["result"]["reason"] == "repetition")
        latest = game["moves"][-1]
        side = latest["player"]
        other = "D" if side == "A" else "A"
        history = tuple(get_state_key(event["board_before"], event["player"]) for event in game["moves"][:-1])
        board = tuple(map(tuple, latest["board_before"]))
        repeat = tuple(map(tuple, latest["move"]))
        self.assertEqual(check_winner(apply_move(board, repeat, side), other,
                                      history + (get_state_key(board, side),)), "DRAW")
        options = SearchOptions(max_depth=1, draw_policy=True)
        chosen = choose_enhanced(board, side, history=history, deadline=inf, options=options,
                                 evaluator=lambda *_: -50)
        self.assertEqual(check_winner(apply_move(board, chosen, side), other,
                                      history + (get_state_key(board, side),)), "DRAW")

    def test_nonrepeating_cache_entry_does_not_mask_new_repetition(self):
        board = initial_board()
        history = tuple(get_state_key(apply_move(board, move, "A"), "D") for move in get_legal_moves(board, "A"))
        stats = dict(nodes=0, cutoffs=0, tt_hint_hits=0)
        engine = EnhancedSearch("A", inf, lambda *_: 50, SearchOptions(1), stats)
        self.assertEqual(engine.visit(board, "A", 1, -inf, inf, ())[0], 50)
        self.assertEqual(engine.visit(board, "A", 1, -inf, inf, history)[0], 0)


def board_with(pieces):
    board = [["."] * 9 for _ in range(9)]
    board[4][4] = "X"
    for (row, col), piece in pieces.items():
        board[row][col] = piece
    return tuple(map(tuple, board))


class FeatureRules(unittest.TestCase):
    def test_fully_blocked_is_maximum_distance_and_edge_is_zero(self):
        castle = board_with({(4,4):"K", (4,3):"A", (4,5):"A", (3,4):"D", (5,4):"D"})
        self.assertEqual(king_escape_distance(castle, (4,4)), 1.0)
        self.assertEqual(king_escape_distance(board_with({(0,4):"K"}), (0,4)), 0.0)

    def test_capture_feature_matches_legal_simulation_at_and_around_castle(self):
        fixtures = (
            ({(4,4):"K", (4,3):"A", (3,4):"A", (5,4):"A", (3,5):"A"}, (4,4), True),
            ({(4,5):"K", (3,5):"A", (5,5):"A", (4,8):"A"}, (4,5), True),
            ({(4,5):"K", (3,5):"A", (5,5):"D", (4,8):"A"}, (4,5), False),
            ({(2,2):"K", (2,1):"A", (0,3):"A"}, (2,2), True),
            ({(4,4):"K", (4,3):"A", (3,4):"A", (5,4):"A"}, (4,4), False),
        )
        for pieces, king, expected in fixtures:
            with self.subTest(king=king, pieces=pieces):
                board = board_with(pieces)
                actual = any(apply_move(board, move, "A")[king[0]][king[1]] != "K"
                             for move in get_legal_moves(board, "A"))
                self.assertEqual(actual, expected)
                self.assertEqual(immediate_king_threat(board, king), float(actual))

    def test_capture_feature_matches_simulation_on_reachable_positions(self):
        rng = Random(91)
        board, side = initial_board(), "A"
        for _ in range(80):
            if check_winner(board, side):
                board, side = initial_board(), "A"
            king = next((r,c) for r in range(9) for c in range(9) if board[r][c]=="K")
            actual = any(apply_move(board, move, "A")[king[0]][king[1]] != "K"
                         for move in get_legal_moves(board, "A"))
            self.assertEqual(immediate_king_threat(board, king), float(actual))
            board = apply_move(board, rng.choice(get_legal_moves(board, side)), side)
            side = "D" if side == "A" else "A"
