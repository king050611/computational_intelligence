"""Elitist genetic optimization; fitness is measured by official matches."""
import contextlib
import os
import json
from tempfile import NamedTemporaryFile
from pathlib import Path
from random import Random
from config.evolution import BASE_WEIGHTS, GENE_SIGNS

def project(weights,config):
    if len(weights)!=6:
        raise ValueError("Six genes are required")
    return tuple(max(0 if config.constrained and sign>0 else -config.bound,
                     min(0 if config.constrained and sign<0 else config.bound,w))
                 for w,sign in zip(weights,GENE_SIGNS))


def perturb(weights,rng,config,*,initial=False):
    return project(tuple(w+rng.gauss(0,config.sigma) if initial or rng.random()<config.mutation else w for w in weights),config)


def fitness(standings,win_reward=3):
    if standings["games"]<=0 or win_reward not in (2,3,5):
        raise ValueError("A completed match suite and reward 2, 3 or 5 are required")
    return (win_reward*standings["wins"]+standings["draws"])/(win_reward*standings["games"])


def rank_key(trial):
    if not trial.get("eligible",True):
        return (-1.0,-1.0,-1.0)
    row=trial["standings"]["overall"]
    return trial["fitness"],row["wins"]/row["games"],-row["losses"]/row["games"]


def select_finalists(trials,config,incumbent=None):
    eligible=[t for t in sorted(trials,key=rank_key,reverse=True) if t.get("eligible",True)]
    selected=[]
    for required in (BASE_WEIGHTS,incumbent):
        if required is None:continue
        found=next((t for t in eligible if tuple(t["weights"])==tuple(required)),None)
        if found is None:
            raise RuntimeError("Required baseline/incumbent failed screening")
        if found not in selected:selected.append(found)
    limit=min(config.finalists,config.population)
    for trial in eligible:
        if len(selected)>=limit:break
        if trial not in selected:selected.append(trial)
    if len(selected)<config.elite:
        raise RuntimeError("Not enough safe candidates for elite selection")
    return selected


def opponent_schedule(pairs,has_history,generation):
    names=("enhanced_dynamic","enhanced","historical") if has_history else ("enhanced_dynamic","enhanced")
    proportions=(.5,.25,.25) if has_history else (2/3,1/3)
    amounts=[int(pairs*p) for p in proportions]
    remainder=pairs-sum(amounts)
    order=sorted(range(len(names)),key=lambda i:(pairs*proportions[i]-amounts[i],(i+generation)%len(names)),reverse=True)
    for i in order[:remainder]:amounts[i]+=1
    schedule=[name for name,count in zip(names,amounts) for _ in range(count)]
    Random(f"opponents:{generation}:{pairs}:{has_history}").shuffle(schedule)
    return schedule


def initial_population(config):
    rng=Random(config.seed)
    return [BASE_WEIGHTS]+[perturb(BASE_WEIGHTS,rng,config,initial=True) for _ in range(config.population-1)]

def next_population(ranked,config,generation):
    if not config.elite <= len(ranked) <= config.population:
        raise ValueError("Insufficient finalist fitness")
    rng=Random(f"{config.seed}:generation:{generation}")
    parents=ranked[:max(config.elite,config.population//2)]
    population=[tuple(w) for w in ranked[:config.elite]]
    while len(population)<config.population:
        a,b=rng.choice(parents),rng.choice(parents)
        child=tuple(rng.choice((x,y)) for x,y in zip(a,b)) if rng.random()<config.crossover else tuple(a)
        population.append(perturb(child,rng,config))
    if BASE_WEIGHTS not in population:
        population[-1]=BASE_WEIGHTS
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


