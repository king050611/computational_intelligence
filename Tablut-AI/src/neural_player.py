"""Neural value + Alpha–Beta, or neural policy and value + MCTS."""
from dataclasses import dataclass
from math import sqrt
from time import perf_counter

from src.game import apply_move, check_winner, get_legal_moves, get_state_key, initial_board, parse_board
from src.neural import OUTCOME_VALUE, action_id
from src.search import TimeManager, choose_move


def other_side(side):
    return "D" if side == "A" else "A"


@dataclass
class Edge:
    move: tuple
    prior: float
    child: object = None

    def score(self, sign, exploration):
        visits = self.child.visits if self.child is not None else 0
        value = self.child.value_sum / visits if visits else 0.0
        return sign * value + exploration * self.prior / (1 + visits)


@dataclass
class Node:
    board: tuple
    side: str
    edges: object = None
    terminal_value: float = 0.0
    visits: int = 0
    value_sum: float = 0.0

    def expand(self, model, moves, noise=None):
        value, priors = model.predict(self.board, self.side, [action_id(move) for move in moves])
        if noise is not None:
            priors = 0.75 * priors + 0.25 * noise.dirichlet([0.3] * len(moves))
        self.edges = [Edge(move, float(prior)) for move, prior in zip(moves, priors)]
        return value


def monte_carlo_search(model, board, side, simulations, *, history=(), deadline=float("inf"),
                       noise=None, sample_move=False):
    """PUCT with defender-perspective backup and the rule engine's repetition checks."""
    if simulations < 1:
        raise ValueError("MCTS requires at least one simulation")
    if sample_move and noise is None:
        raise ValueError("Sampling a move requires a random generator")
    root = Node(board, side)
    moves = get_legal_moves(board, side)
    if not moves:
        raise ValueError("No legal moves")
    root.expand(model, moves, noise)
    for _ in range(simulations):
        if perf_counter() >= deadline:
            break
        node = root
        path = [root]
        ancestors = set(history)
        while node.edges and perf_counter() < deadline:
            ancestors.add(get_state_key(node.board, node.side))
            sign = 1 if node.side == "D" else -1
            exploration = 1.5 * sqrt(max(1, node.visits))
            edge = max(node.edges, key=lambda child: child.score(sign, exploration))
            if edge.child is None:
                edge.child = Node(apply_move(node.board, edge.move, node.side), other_side(node.side))
            node = edge.child
            path.append(node)
        if perf_counter() >= deadline:
            break
        if node.edges is None:
            winner = check_winner(node.board, node.side, ancestors)
            if winner:
                node.edges = ()
                node.terminal_value = OUTCOME_VALUE[winner]
            else:
                value = node.expand(model, get_legal_moves(node.board, node.side))
        if not node.edges:
            value = node.terminal_value
        for visited in path:
            visited.visits += 1
            visited.value_sum += value

    counts = [edge.child.visits if edge.child is not None else 0 for edge in root.edges]
    total = sum(counts)
    weights = counts if total else [edge.prior for edge in root.edges]
    total = sum(weights)
    probabilities = [weight / total for weight in weights]
    if sample_move:
        index = int(noise.choice(len(moves), p=probabilities))
    else:
        index = max(range(len(moves)), key=probabilities.__getitem__)
    return moves[index], tuple((action_id(move), probability) for move, probability in zip(moves, probabilities))


class NeuralPlayer:
    """Expose the course Player interface for a selected neural checkpoint."""
    def __init__(self, model, phase, simulations, opening=None):
        self.model, self.phase, self.simulations = model, phase, simulations
        self.clock = TimeManager()
        self.opening = initial_board() if opening is None else opening
        self.history = []

    def _play(self, board, side):
        board = parse_board(board)
        start = perf_counter()
        try:
            if self.phase == "value":
                move = choose_move(board, side, self.clock.deadline(), "minimax",
                                   position_value=self.model.value)
            else:
                if not self.history and side == "D":
                    self.history.append(get_state_key(self.opening, "A"))
                move, _ = monte_carlo_search(self.model, board, side, self.simulations,
                                            history=self.history, deadline=self.clock.deadline())
                self.history.append(get_state_key(board, side))
                board_after = apply_move(board, move, side)
                self.history.append(get_state_key(board_after, other_side(side)))
            if move is None:
                raise ValueError("No legal moves")
            return [list(move[0]), list(move[1])]
        finally:
            self.clock.record_elapsed(perf_counter() - start)

    def play_attacker(self, board):
        return self._play(board, "A")

    def play_defender(self, board):
        return self._play(board, "D")
