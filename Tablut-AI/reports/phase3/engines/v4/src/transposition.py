"""Bounded move hints plus a bounds-checked transposition table.

``MoveHints`` never caches scores. ``TranspositionTable`` does cache scores, but only
for positions whose searched subtree contained no repetition hit, so a draw caused by
a specific history can never leak into a different visit of the same board.
"""
from collections import OrderedDict

EXACT, LOWER, UPPER = 0, 1, 2


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
    """Depth/flag/score/move entries with LRU eviction and probe statistics."""

    def __init__(self, capacity):
        self.capacity = int(capacity)
        self.entries = OrderedDict()
        self.hits = 0
        self.stores = 0

    def get(self, key):
        entry = self.entries.get(key)
        return entry[3] if entry else None

    def probe(self, key, depth, alpha, beta):
        if not self.capacity:
            return None
        entry = self.entries.get(key)
        if entry is None:
            return None
        stored_depth, flag, score, _ = entry
        if stored_depth < depth:
            return None
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

    def store(self, key, depth, score, flag, move):
        if not self.capacity:
            return
        entry = self.entries.get(key)
        if entry is not None and entry[0] > depth:
            return
        self.entries[key] = (depth, flag, score, move)
        self.entries.move_to_end(key)
        self.stores += 1
        if len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
