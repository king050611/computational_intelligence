"""Offline tournament using the unmodified official referee."""
import argparse
import contextlib
import importlib.util
import io
import json
import multiprocessing
import os
import random
import sys
from pathlib import Path
from time import perf_counter
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "reference")]
from Tablut import Tablut
from TeamXX import Player
from src.search import choose_move, TimeManager, STRATEGIES


def _external_worker(connection, filename):
    """Separate interpreter module cache prevents src/config name collisions."""
    try:
        filename = Path(filename)
        os.chdir(filename.parent)
        for name in list(sys.modules):
            if name in ("src", "config") or name.startswith(("src.", "config.")):
                del sys.modules[name]
        sys.path = [str(filename.parent)] + [x for x in sys.path if x not in (str(ROOT), str(ROOT/"reference"))]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            spec = importlib.util.spec_from_file_location("external_team", filename)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            bot = module.Player()
            if not all(callable(getattr(bot, name, None)) for name in ("play_attacker", "play_defender")):
                raise TypeError("Player must implement both play methods")
        connection.send((True, None, ""))
        while True:
            request = connection.recv()
            if request is None:
                break
            method, board = request
            log = io.StringIO()
            try:
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    move = getattr(bot, method)(board)
                connection.send((True, move, log.getvalue()))
            except Exception as exc:
                connection.send((False, repr(exc), log.getvalue()))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        connection.send((False, repr(exc), ""))
    finally:
        connection.close()


class ExternalBot:
    def __init__(self, filename):
        ctx = multiprocessing.get_context("spawn")
        self.connection, child = ctx.Pipe()
        self.process = ctx.Process(target=_external_worker, args=(child,str(filename)))
        self.process.start()
        child.close()
        self.log, self.spent = [], 0.0
        try:
            self._receive(10)
        except Exception:
            self.close()
            raise

    def _receive(self, timeout):
        if not self.connection.poll(max(0.01,timeout)):
            raise TimeoutError("External bot exceeded runner response deadline")
        ok, result, log = self.connection.recv()
        self.log.append(log)
        if not ok:
            raise RuntimeError(result)
        return result

    def _play(self, board, method):
        start = perf_counter()
        try:
            self.connection.send((method,board))
            return self._receive(60-self.spent+0.25)
        finally:
            self.spent += perf_counter()-start

    def play_attacker(self, board):
        return self._play(board,"play_attacker")

    def play_defender(self, board):
        return self._play(board,"play_defender")

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=2)
        self.connection.close()


class StrategyBot:
    def __init__(self, strategy, seed):
        self.strategy, self.rng, self.clock = strategy, random.Random(seed), TimeManager()

    def _play(self, board, side):
        start = perf_counter()
        try:
            move = choose_move(board,side,self.clock.deadline(),self.strategy,self.rng)
            return [list(x) for x in move]
        finally:
            self.clock.record_elapsed(perf_counter()-start)

    def play_attacker(self, board):
        return self._play(board,"A")

    def play_defender(self, board):
        return self._play(board,"D")


class Timed:
    def __init__(self, bot):
        self.bot, self.times, self.errors = bot, [], []
        self.invalid_returns = []

    def _play(self, board, side):
        start = perf_counter()
        try:
            move = getattr(self.bot,"play_"+side)(board)
            valid = (isinstance(move,(list,tuple)) and len(move)==2
                     and all(isinstance(pos,(list,tuple)) and len(pos)==2
                             and all(type(n) is int for n in pos) for pos in move))
            if not valid:
                self.invalid_returns.append(repr(move))
                # Give the official referee a safely rejectable illegal action.
                return [[-1,-1],[-1,-1]]
            return move
        except Exception as exc:
            self.errors.append(dict(type=type(exc).__name__,message=str(exc)))
            raise
        finally:
            self.times.append(perf_counter()-start)

    def play_attacker(self, board):
        return self._play(board,"attacker")

    def play_defender(self, board):
        return self._play(board,"defender")


def standings(results):
    def tally(rows):
        wins=sum(x["winner"]==x["our_side"] for x in rows)
        draws=sum(x["winner"]=="DRAW" for x in rows)
        return dict(games=len(rows),wins=wins,draws=draws,losses=len(rows)-wins-draws,points=2*wins+draws)
    return dict(overall=tally(results),attacker=tally([x for x in results if x["our_side"]=="A"]),
                defender=tally([x for x in results if x["our_side"]=="D"]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games",type=int,default=10)
    parser.add_argument("--strategy",choices=STRATEGIES,default="adaptive")
    opponents=parser.add_mutually_exclusive_group()
    opponents.add_argument("--opponent",choices=STRATEGIES,default="random")
    opponents.add_argument("--opponent-file",type=Path)
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.games<=0:
        parser.error("--games must be positive")
    if args.opponent_file and (not args.opponent_file.is_file() or args.opponent_file.suffix.lower()!=".py"):
        parser.error("--opponent-file must be an existing Python file")
    results=[]
    for i in range(args.games):
        side="A" if i%2==0 else "D"
        external=ExternalBot(args.opponent_file.resolve()) if args.opponent_file else None
        try:
            ours=Timed(Player() if args.strategy=="adaptive" else StrategyBot(args.strategy,args.seed+i))
            other=Timed(external or StrategyBot(args.opponent,args.seed+i))
            a,d=(ours,other) if side=="A" else (other,ours)
            game=Tablut()
            start=perf_counter()
            with contextlib.redirect_stdout(io.StringIO()) as log:
                game.play(a,d)
            message=log.getvalue()
            # Referee reports which side caused an error; preserve details as well.
            issues={}
            for label,word,bot in (("A","Attackers",a),("D","Defenders",d)):
                issues[label]=dict(illegal_moves=message.count("Illegal move by "+word),
                                  timeouts=message.count(word+" exceeded time limit") + sum(e["type"]=="TimeoutError" for e in bot.errors),
                                  exceptions=len(bot.errors),details=bot.errors,invalid_returns=bot.invalid_returns)
            results.append(dict(game=i+1,our_side=side,winner=game.winner or "DRAW",plies=game.rounds_played,
                                elapsed_seconds=perf_counter()-start,attacker_seconds=sum(a.times),defender_seconds=sum(d.times),
                                our_mean_move_seconds=sum(ours.times)/max(1,len(ours.times)),our_max_move_seconds=max(ours.times,default=0),
                                illegal_moves=sum(x["illegal_moves"] for x in issues.values()),
                                timeouts=sum(x["timeouts"] for x in issues.values()),exceptions=sum(x["exceptions"] for x in issues.values()),
                                issues=issues,log=message,opponent_log="".join(external.log) if external else ""))
        finally:
            if external:
                external.close()
    table=standings(results)
    summary=dict(version="2.0",strategy=args.strategy,opponent=str(args.opponent_file.resolve()) if args.opponent_file else args.opponent,
                 seed=args.seed,games=args.games,standings=table,our_win_rate=table["overall"]["wins"]/args.games,results=results)
    for label,row in table.items():
        print(f"{label:10} W {row['wins']} D {row['draws']} L {row['losses']} Points {row['points']}/{2*row['games']}")
    print("Illegal moves / timeouts / exceptions:",*[sum(x[k] for x in results) for k in ("illegal_moves","timeouts","exceptions")])
    output=args.output or ROOT/"reports"/"experiments"/"latest_v2.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print("JSON:",output)
    if any(x["illegal_moves"] or x["timeouts"] or x["exceptions"] for x in results):
        raise SystemExit(1)


if __name__=="__main__":
    multiprocessing.freeze_support()
    main()
