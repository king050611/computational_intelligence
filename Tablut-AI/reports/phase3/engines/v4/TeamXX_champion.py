"""External control bot: frozen V4 engine + V4 champion evaluator."""
from pathlib import Path

from src.evaluation import load_evaluator
from src.experimental_player import ExperimentalPlayer
from src.game import initial_board

MODEL = Path(r"D:\workstudy\大四\大四上\computational_intelligence\Tablut-AI\reports\training\v4_champion_archive\best.json")


class Player:
    def __init__(self):
        self.bot = ExperimentalPlayer("evolutionary_dynamic", evaluator=load_evaluator(MODEL),
                                      opening=initial_board())

    def play_attacker(self, board):
        return self.bot.play_attacker(board)

    def play_defender(self, board):
        return self.bot.play_defender(board)
