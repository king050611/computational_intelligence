"""Course entry point for the frozen independent role engines."""
from src.experimental_player import ExperimentalPlayer
from src.game import initial_board
from src.role_player import RolePlayer

class LegacyPlayer(ExperimentalPlayer):
    def __init__(self, record_search=False):
        super().__init__("enhanced_dynamic",record_search=record_search, opening=initial_board())

def independent_player(record_search=False):
    return IndependentPlayer(record_search=record_search)


class IndependentPlayer(RolePlayer):
    """Course coordinate protocol for the isolated engines."""

    def __init__(self, record_search=False):
        super().__init__(record_search=record_search, verify_attacker=True)

    def play_attacker(self, board):
        return [list(square) for square in super().play_attacker(board)]

    def play_defender(self, board):
        return [list(square) for square in super().play_defender(board)]


Player = IndependentPlayer
