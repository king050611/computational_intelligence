"""Official evaluation adapter; rename XX to your assigned team number."""
from src.agents.attacker import choose_attacker_move
from src.agents.defender import choose_defender_move


class Player:
    @staticmethod
    def _external(move):
        # The official game checks no-move draws before asking for a move.
        if move is None:
            raise ValueError("No legal move: game should already be over")
        return [list(move[0]), list(move[1])]

    def play_attacker(self, board):
        return self._external(choose_attacker_move(board))

    def play_defender(self, board):
        return self._external(choose_defender_move(board))
