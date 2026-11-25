"""Elitist genetic optimization; fitness is measured by official matches."""
import contextlib
import os
import json
from tempfile import NamedTemporaryFile
from pathlib import Path
from random import Random
from config.evolution import BASE_WEIGHTS

def perturb(weights,rng,config,*,initial=False):
    return tuple(max(-config.bound,min(config.bound,w+rng.gauss(0,config.sigma))) if initial or rng.random()<config.mutation else w for w in weights)

def initial_population(config):
    rng=Random(config.seed)
    return [BASE_WEIGHTS]+[perturb(BASE_WEIGHTS,rng,config,initial=True) for _ in range(config.population-1)]

def next_population(ranked,config,generation):
    if len(ranked)!=config.population:
        raise ValueError("Incomplete population fitness")
    rng=Random(f"{config.seed}:generation:{generation}")
    parents=ranked[:max(config.elite,config.population//2)]
    population=[tuple(w) for w in ranked[:config.elite]]
    while len(population)<config.population:
        a,b=rng.choice(parents),rng.choice(parents)
        child=tuple(rng.choice((x,y)) for x,y in zip(a,b)) if rng.random()<config.crossover else tuple(a)
        population.append(perturb(child,rng,config))
    return population


def save_checkpoint(directory, checkpoint):
    """Publish a complete checkpoint without overwriting one from another process."""
    destination = directory / f"checkpoint-{checkpoint['generation']:04d}.json"
    file = NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False)
    temporary = Path(file.name)
    try:
        with file:
            json.dump(checkpoint, file, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            file.write("\n")
        os.link(temporary, destination)
    finally:
        temporary.unlink()
    return destination



@contextlib.contextmanager
def training_lock(directory):
    """Prevent competing writers to a run. The OS releases the lock on process exit."""
    with (directory / ".training.lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt

                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f"Could not lock {directory}. Check for another active trainer.") from exc
        yield


