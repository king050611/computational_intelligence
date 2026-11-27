"""Official standard-library bot. Learned models are never loaded implicitly."""
from src.experimental_player import ExperimentalPlayer
from src.game import initial_board

class Player(ExperimentalPlayer):
    def __init__(self, record_search=False):
        super().__init__("enhanced_dynamic",record_search=record_search, opening=initial_board())
