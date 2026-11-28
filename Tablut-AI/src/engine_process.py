"""Isolate engine imports and clocks behind a standard-library process protocol."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys


def worker(spec):
    sys.path.insert(0,spec["engine"])
    from config.experimental import SearchOptions
    from src.evaluation import load_evaluator
    from src.experimental_player import ExperimentalPlayer
    from src import time_control
    import src.experimental_player as adapter
    for module in (time_control,adapter):
        if hasattr(module,"GAME_TIME_LIMIT"):
            module.GAME_TIME_LIMIT=spec["seconds"]
    settings={"max_depth":spec["depth"]}
    if spec["nodes"]:
        settings["node_budget"]=spec["nodes"]
    settings.update(spec.get("search_options", {}))
    model=load_evaluator(spec["model"]) if spec["model"] else None
    bot=ExperimentalPlayer("evolutionary_dynamic" if model else "enhanced_dynamic",
                           opening=spec["board"],evaluator=model,options=SearchOptions(**settings),record_search=True)
    print("ready",flush=True)
    for line in sys.stdin:
        side,board=json.loads(line)
        move=(bot.play_attacker if side=="A" else bot.play_defender)(board)
        print(json.dumps([move,bot.last_search_stats]),flush=True)


class Engine:
    def __init__(self,spec,board):
        self.process=subprocess.Popen([sys.executable,"-I","-B",__file__,json.dumps(dict(spec,board=board))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding="utf-8",bufsize=1)
        self.reader=ThreadPoolExecutor(max_workers=1)
        self.seconds=spec["seconds"]
        try:
            if self.read_line(10).strip()!="ready":
                raise RuntimeError(f"Engine startup failed for {spec['engine']}")
        except BaseException:
            self.close()
            raise
        self.last_search_stats=None

    def read_line(self,seconds):
        try:
            return self.reader.submit(self.process.stdout.readline).result(timeout=seconds)
        except TimeoutError:
            self.process.kill()
            raise TimeoutError("Engine exceeded response deadline") from None

    def play(self,side,board):
        self.process.stdin.write(json.dumps([side,board])+"\n")
        self.process.stdin.flush()
        move,self.last_search_stats=json.loads(self.read_line(self.seconds))
        return move

    def play_attacker(self,board):
        return self.play("A",board)

    def play_defender(self,board):
        return self.play("D",board)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.reader.shutdown(wait=True)
        self.process.stdout.close()


if __name__ == "__main__":
    worker(json.loads(sys.argv[1]))
