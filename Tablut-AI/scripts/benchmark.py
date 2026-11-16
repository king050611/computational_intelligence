"""Compare greedy with first/random baselines, alternating sides."""
import argparse
import contextlib
import io
import json
import random
import sys
from pathlib import Path
from time import perf_counter
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "reference")]
from Tablut import Tablut
from TeamXX import Player
from src.search import choose_move


class Baseline:
    def __init__(self, strategy, seed):
        self.strategy, self.rng = strategy, random.Random(seed)

    def play_attacker(self, board):
        return [list(x) for x in choose_move(board,"A",strategy=self.strategy,rng=self.rng)]

    def play_defender(self, board):
        return [list(x) for x in choose_move(board,"D",strategy=self.strategy,rng=self.rng)]


class Timed:
    def __init__(self, bot):
        self.bot, self.times = bot, []

    def _play(self, board, side):
        start = perf_counter()
        try:
            return getattr(self.bot,"play_" + side)(board)
        finally:
            self.times.append(perf_counter()-start)

    def play_attacker(self, board):
        return self._play(board,"attacker")

    def play_defender(self, board):
        return self._play(board,"defender")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games",type=int,default=10)
    parser.add_argument("--opponent",choices=["first","random","greedy"],default="random")
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    if args.games <= 0:
        parser.error("--games must be positive")
    results=[]
    for i in range(args.games):
        side = "A" if i%2==0 else "D"
        ours = Timed(Player())
        opponent = Timed(Player() if args.opponent=="greedy" else Baseline(args.opponent,args.seed+i))
        a,d = (ours,opponent) if side=="A" else (opponent,ours)
        game = Tablut()
        start = perf_counter()
        with contextlib.redirect_stdout(io.StringIO()) as log:
            game.play(a,d)
        message=log.getvalue()
        results.append(dict(game=i+1,greedy_side=side,winner=game.winner or "DRAW",
                            plies=game.rounds_played,elapsed_seconds=perf_counter()-start,
                            attacker_seconds=sum(a.times),defender_seconds=sum(d.times),
                            greedy_mean_move_seconds=sum(ours.times)/max(1,len(ours.times)),
                            greedy_max_move_seconds=max(ours.times,default=0),
                            illegal_moves=message.count("Illegal move"),
                            timeouts=message.count("exceeded time limit"),exceptions=message.count("Exception caught"),log=message))
    summary=dict(strategy="greedy",opponent=args.opponent,seed=args.seed,games=args.games,
                 greedy_win_rate=sum(x["winner"]==x["greedy_side"] for x in results)/args.games,
                 attacker_win_rate=sum(x["winner"]=="A" for x in results)/args.games,
                 defender_win_rate=sum(x["winner"]=="D" for x in results)/args.games,
                 draw_rate=sum(x["winner"]=="DRAW" for x in results)/args.games,results=results)
    content=json.dumps(summary,indent=2)
    print(content)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(content,encoding="utf-8")
    if any(x["illegal_moves"] or x["timeouts"] or x["exceptions"] for x in results):
        raise SystemExit(1)


if __name__=="__main__":
    main()
