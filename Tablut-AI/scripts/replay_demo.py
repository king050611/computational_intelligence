"""Record official matches as JSON plus a self-contained visual replay. Demo only."""
import argparse
import contextlib
import copy
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

# Import adapters first: benchmark sets up the project and reference paths.
from benchmark import ROOT, StrategyBot, Timed
from Tablut import Tablut
from TeamXX import Player
from src.search import STRATEGIES


def snapshot(board):
    return [list(row) for row in board]


class Recorder(Tablut):
    def __init__(self):
        super().__init__()
        self.initial_board = snapshot(self.board)
        self.events = []
        self.pending = None
        self.termination = None

    def make_move(self, is_attacker, moves):
        before = snapshot(self.board)
        legal = super().make_move(is_attacker, moves)
        event = self.pending
        self.pending = None
        event.update(accepted=legal, status="played" if legal else "illegal_move",
                     board_before=before, board_after=snapshot(self.board), captures=[])
        if legal:
            start, end = moves
            event.update(from_square=list(start), to_square=list(end), piece=before[start[0]][start[1]])
            for r in range(9):
                for c in range(9):
                    if [r,c] != list(start) and before[r][c] in "ADK" and self.board[r][c] in ".X":
                        event["captures"].append(dict(piece=before[r][c],square=[r,c]))
        self.events.append(event)
        return legal

    def check_if_game_over(self, is_attacker_next):
        with contextlib.redirect_stdout(io.StringIO()) as log:
            over = super().check_if_game_over(is_attacker_next)
        message = log.getvalue()
        print(message, end="")
        if over:
            if self.winner == "A":
                reason = "king_captured"
            elif self.winner == "D":
                reason = "king_escaped" if any(self.board[r][c]=="K" and (r in (0,8) or c in (0,8)) for r in range(9) for c in range(9)) else "fewer_than_two_attackers"
            else:
                reason = "repetition" if "Repeated position" in message else "no_legal_moves"
            self.termination = dict(winner=self.winner or "DRAW",reason=reason)
        self.events[-1]["result_after"] = dict(terminal=over,winner=self.winner if over else None,
                                                next_player=None if over else "A" if is_attacker_next else "D")
        return over


class ObservedPlayer:
    def __init__(self, bot, recorder, strategy):
        self.timed, self.recorder, self.strategy = Timed(bot), recorder, strategy

    def _play(self, board, side):
        event = dict(ply=len(self.recorder.events)+1,round=len(self.recorder.events)//2+1,
                     player=side,strategy=self.strategy,move=None,from_square=None,to_square=None,
                     piece=None,captures=[],board_before=snapshot(board))
        self.recorder.pending = event
        start = perf_counter()
        try:
            play = self.timed.play_attacker if side=="A" else self.timed.play_defender
            move = play(board)
            event["move"] = [list(x) for x in move]
            if self.timed.invalid_returns:
                event["invalid_return"] = self.timed.invalid_returns[-1]
            return move
        except Exception as exc:
            event["error"] = dict(type=type(exc).__name__,message=str(exc))
            raise
        finally:
            event["elapsed_seconds"] = perf_counter()-start
            event["search"] = copy.deepcopy(getattr(self.timed.bot, "last_search_stats", None))

    def play_attacker(self, board):
        return self._play(board,"A")

    def play_defender(self, board):
        return self._play(board,"D")


def record_game(index, strategy, opponent, seed):
    game = Recorder()
    our_side = "A" if index%2==0 else "D"
    ours = Player(record_search=True) if strategy=="adaptive" else StrategyBot(strategy,seed,record_search=True)
    other = StrategyBot(opponent,seed,record_search=True)
    ours = ObservedPlayer(ours,game,strategy)
    other = ObservedPlayer(other,game,opponent)
    attacker, defender = (ours,other) if our_side=="A" else (other,ours)
    with contextlib.redirect_stdout(io.StringIO()) as log:
        game.play(attacker,defender)
    message = log.getvalue()
    if game.termination is None:
        reason = "timeout" if "exceeded time limit" in message else "exception" if "Exception caught" in message else "illegal_move"
        game.termination = dict(winner=game.winner or "DRAW",reason=reason)
        if game.pending is not None:
            game.pending.update(accepted=False,status=reason,board_after=snapshot(game.board))
            game.events.append(game.pending)
        game.events[-1]["result_after"] = dict(terminal=True,winner=game.winner,next_player=None)
    for event in game.events:
        event.setdefault("result_after",dict(terminal=False,winner=None,next_player=None))
    return dict(game=index+1,our_side=our_side,seed=seed,
                strategies=dict(A=attacker.strategy,D=defender.strategy),
                initial_board=game.initial_board,moves=game.events,final_board=snapshot(game.board),
                result=game.termination,accepted_moves=sum(x["accepted"] for x in game.events),
                attacker_seconds=sum(attacker.timed.times),defender_seconds=sum(defender.timed.times),
                referee_log=message)


def write_replay(data, output):
    output.mkdir(parents=True,exist_ok=True)
    json_path=output/"games.json"
    json_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    template=(Path(__file__).with_name("replay_template.html")).read_text(encoding="utf-8")
    # Embedded JSON allows file:// viewing with no server/fetch/CORS requirement.
    payload=json.dumps(data,ensure_ascii=False).replace("<", chr(92) + "u003c")
    (output/"replay.html").write_text(template.replace("__REPLAY_DATA__",payload),encoding="utf-8")
    return json_path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games",type=int,default=2)
    parser.add_argument("--strategy",choices=STRATEGIES,default="adaptive")
    parser.add_argument("--opponent",choices=STRATEGIES,default="random")
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--output-dir",type=Path,default=ROOT/"reports"/"replays"/"latest")
    args=parser.parse_args()
    if args.games<1:
        parser.error("--games must be positive")
    data=dict(schema_version="1.1",created_at=datetime.now(timezone.utc).isoformat(),
              coordinates="zero-based [row, column]",symbols={"A":"attacker","D":"defender","K":"king","X":"empty castle",".":"empty"},
              note="Demo observation adds overhead. Nodes count alpha-beta recursion only; null means unrecorded.",
              games=[record_game(i,args.strategy,args.opponent,args.seed+i) for i in range(args.games)])
    path=write_replay(data,args.output_dir)
    for game in data["games"]:
        print(f"Game {game['game']}: {game['accepted_moves']} moves; {game['result']}")
    print("JSON:",path.resolve())
    print("Replay:",(args.output_dir/"replay.html").resolve())


if __name__=="__main__":
    main()
