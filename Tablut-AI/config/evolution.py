"""Win-oriented, two-stage genetic experiments; formal bot defaults stay separate."""
from dataclasses import dataclass
from math import isfinite

BASE_WEIGHTS = (-400.0,600.0,-160.0,0.0,0.0,0.0)
GENE_SIGNS = (-1,1,-1,-1,1,-1)

@dataclass(frozen=True)
class EvolutionConfig:
    population: int = 8
    elite: int = 2
    crossover: float = 0.7
    mutation: float = 0.2
    sigma: float = 80.0
    bound: float = 1000.0
    seed: int = 42
    win_reward: int = 3
    constrained: bool = True
    quick_pairs: int = 2
    quick_depth: int = 2
    finalists: int = 4
    final_pairs: int = 6
    # V3 training-mechanism knobs: weight-unique populations and a diversity slot.
    dedup_attempts: int = 64
    diversity_slots: int = 1
    # V4: a diversity candidate must be within this screening-fitness margin of the
    # manual baseline before weight distance is even considered.
    diversity_margin: float = 0.10

    def __post_init__(self):
        integers=(self.population,self.elite,self.seed,self.win_reward,self.quick_pairs,self.quick_depth,self.finalists,self.final_pairs)
        if any(type(v) is not int for v in integers) or self.seed<0:
            raise ValueError("Counts and seed must be integers, seed nonnegative")
        if not 1 <= self.elite < self.population or not max(2,self.elite) <= min(self.finalists,self.population):
            raise ValueError("Require population > elite >= 1 and sufficient finalists")
        if min(self.quick_pairs,self.quick_depth,self.finalists,self.final_pairs)<1 or self.win_reward not in (2,3,5):
            raise ValueError("Positive screening sizes and win reward 2, 3 or 5 are required")
        if not all(isfinite(v) for v in (self.crossover,self.mutation,self.sigma,self.bound)) or not 0<=self.crossover<=1 or not 0<=self.mutation<=1 or self.sigma<=0 or self.bound<600 or type(self.constrained) is not bool:
            raise ValueError("Invalid genetic probability, mutation scale or weight bounds")
        if type(self.dedup_attempts) is not int or self.dedup_attempts<1:
            raise ValueError("dedup_attempts must be a positive integer")
        if type(self.diversity_slots) is not int or not 0<=self.diversity_slots<=max(0,self.finalists-1):
            raise ValueError("diversity_slots must be a nonnegative integer below finalists")
        if not isfinite(self.diversity_margin) or not 0<=self.diversity_margin<=1:
            raise ValueError("diversity_margin must be a probability between 0 and 1")
