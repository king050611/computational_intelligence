"""Bounded move hints plus a bounds-checked transposition table.

``MoveHints`` never caches scores. ``TranspositionTable`` does cache scores, but only
only within an equal ancestry context. Even a subtree that did not repeat in one
context may repeat under a different set of ancestors. Move hints can still be reused.

Mate scores are stored relative to the node (``score + ply`` for a win, ``score - ply``
for a loss) and converted back on probe, so a proven win found at one ply is still
recognised as the same distance-to-mate when reached along a different path.
"""
from collections import OrderedDict

EXACT, LOWER, UPPER = 0, 1, 2

MATE_SCORE = 1_000_000_000.0
MATE_BOUND = MATE_SCORE - 1_000.0


def to_table(score, ply):
    """Convert a root-perspective score into a node-relative table score."""
    if score >= MATE_BOUND:
        return score + ply
    if score <= -MATE_BOUND:
        return score - ply
    return score


def from_table(score, ply):
    """Convert a node-relative table score back into a root-perspective score."""
    if score >= MATE_BOUND:
        return score - ply
    if score <= -MATE_BOUND:
        return score + ply
    return score


class MoveHints:
    def __init__(self, capacity):
        self.capacity = capacity
        self.entries = OrderedDict()

    def get(self, key):
        entry = self.entries.get(key)
        return entry[1] if entry else None

    def put(self, key, depth, move):
        if not self.capacity:
            return
        entry = self.entries.get(key)
        if entry and entry[0] > depth:
            return
        self.entries[key] = (depth, move)
        self.entries.move_to_end(key)
        if len(self.entries) > self.capacity:
            self.entries.popitem(last=False)


class TranspositionTable:
    """Depth/flag/score/move entries with LRU eviction and mate-distance normalisation."""

    def __init__(self, capacity):
        self.capacity = int(capacity)
        self.entries = OrderedDict()
        self.hits = 0
        self.stores = 0

    def get(self, key):
        entry = self.entries.get(key)
        return entry[3] if entry else None

    def probe(self, key, depth, alpha, beta, ply=0, *, context=None):
        if not self.capacity:
            return None
        entry = self.entries.get(key)
        if entry is None:
            return None
        stored_depth, flag, stored, _, stored_context = entry
        if stored_context != context:
            return None
        if stored_depth < depth:
            return None
        score = from_table(stored, ply)
        if flag == EXACT:
            self.hits += 1
            return score
        if flag == LOWER and score >= beta:
            self.hits += 1
            return score
        if flag == UPPER and score <= alpha:
            self.hits += 1
            return score
        return None

    def store(self, key, depth, score, flag, move, ply=0, *, context=None):
        if not self.capacity:
            return
        entry = self.entries.get(key)
        if entry is not None and entry[0] > depth and entry[4] == context:
            return
        self.entries[key] = (depth, flag, to_table(score, ply), move, context)
        self.entries.move_to_end(key)
        self.stores += 1
        if len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
