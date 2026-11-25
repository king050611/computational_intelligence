"""Bounded move hints only: a repeated board can score differently by path."""
from collections import OrderedDict


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
