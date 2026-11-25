"""Initial genetic experiment settings; not proven competitive defaults."""
from dataclasses import dataclass
from math import isfinite

BASE_WEIGHTS = (-400.0,600.0,-160.0,0.0,0.0,0.0)

@dataclass(frozen=True)
class EvolutionConfig:
    population: int = 12
    elite: int = 2
    crossover: float = 0.7
    mutation: float = 0.2
    sigma: float = 80.0
    bound: float = 2000.0
    seed: int = 42

    def __post_init__(self):
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("Seed must be a nonnegative integer")
        if type(self.population) is not int or type(self.elite) is not int or not 1 <= self.elite < self.population:
            raise ValueError("Require population > elite >= 1")
        if not all(isfinite(v) for v in (self.crossover,self.mutation,self.sigma,self.bound)) or not 0 <= self.crossover <= 1 or not 0 <= self.mutation <= 1 or self.sigma <= 0 or self.bound < 600:
            raise ValueError("Invalid evolution probabilities, mutation scale or weight bound")
