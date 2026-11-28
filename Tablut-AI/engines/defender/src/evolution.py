"""Elitist genetic optimization with weight-unique populations and diversity selection.

V3 keeps the V2 genetic operators and adds three training-mechanism guarantees that
never touch the search engine, the six features or the formal bot:

* every population carries weight-unique genomes (exact numeric comparison);
* every finalist slot carries a different weight vector;
* one finalist slot is reserved for a qualified but weight-distant candidate.

Fitness is still measured by official matches; nothing here changes the referee.
"""
import contextlib
import os
import json
from math import fsum, sqrt
from tempfile import NamedTemporaryFile
from pathlib import Path
from random import Random
from config.evolution import BASE_WEIGHTS, GENE_SIGNS


def project(weights,config):
    if len(weights)!=len(BASE_WEIGHTS):
        raise ValueError(f"{len(BASE_WEIGHTS)} genes are required")
    return tuple(max(0 if config.constrained and sign>0 else -config.bound,
                     min(0 if config.constrained and sign<0 else config.bound,w))
                 for w,sign in zip(weights,GENE_SIGNS))


def perturb(weights,rng,config,*,initial=False):
    return project(tuple(w+rng.gauss(0,config.sigma) if initial or rng.random()<config.mutation else w for w in weights),config)


def weight_distance(weights,reference,scale):
    """Normalized Euclidean distance used by the diversity slot.

    ``scale`` is the weight bound, so distances are comparable across generations
    without introducing another hand-tuned parameter.
    """
    weights,reference=tuple(weights),tuple(reference)
    if len(weights)!=len(reference) or not scale or scale<=0:
        raise ValueError("Distance needs two equal-length vectors and a positive scale")
    return sqrt(fsum(((w-r)/scale)**2 for w,r in zip(weights,reference)))


def deduplicate(population):
    """Drop exact duplicate genomes while preserving order."""
    unique=[]
    for genome in population:
        genome=tuple(genome)
        if genome not in unique:
            unique.append(genome)
    return unique


def population_report(population):
    genomes=[tuple(w) for w in population]
    distinct=len(set(genomes))
    return dict(size=len(genomes),distinct=distinct,duplicates=len(genomes)-distinct)


def mutate_distinct(weights,population,rng,config):
    """Mutate into a genome absent from ``population``; raise instead of looping forever."""
    for _ in range(config.dedup_attempts):
        candidate=perturb(weights,rng,config,initial=True)
        if candidate!=tuple(weights) and candidate not in population:
            return candidate
    raise RuntimeError(f"No weight-unique mutant after {config.dedup_attempts} attempts; "
                       "reduce sigma/bound or enlarge the search space")


def initial_population(config,seed_weights=None):
    """Build a weight-unique seed population; manual baseline and seed always survive."""
    rng=Random(config.seed)
    seeds=[tuple(BASE_WEIGHTS)]
    if seed_weights is not None:
        champion=project(tuple(seed_weights),config)
        if champion not in seeds:
            seeds.append(champion)
    population=[tuple(w) for w in seeds[:config.population]]
    attempts=0
    limit=max(1,config.population)*config.dedup_attempts
    while len(population)<config.population:
        attempts+=1
        if attempts>limit:
            raise RuntimeError("Could not build a weight-unique initial population")
        parent=population[rng.randrange(len(population))]
        population.append(mutate_distinct(parent,population,rng,config))
    return population


def next_population(ranked,config,generation,*,incumbent=None):
    """Elites plus offspring, always weight-unique, always keeping baseline and champion."""
    if not config.elite<=len(ranked)<=config.population:
        raise ValueError("Insufficient finalist fitness")
    rng=Random(f"{config.seed}:generation:{generation}")
    genomes=[tuple(w) for w in ranked]
    seeds=[tuple(BASE_WEIGHTS)]
    if incumbent is not None:
        champion=project(tuple(incumbent),config)
        if champion not in seeds:
            seeds.append(champion)
    for genome in genomes[:config.elite]:
        if len(seeds)>=config.population:
            break
        if genome not in seeds:
            seeds.append(genome)
    population=deduplicate(seeds)[:config.population]
    parents=genomes[:max(config.elite,config.population//2)]
    attempts=0
    limit=max(1,config.population)*config.dedup_attempts
    while len(population)<config.population:
        attempts+=1
        if attempts>limit:
            raise RuntimeError("Could not build a weight-unique next population")
        a,b=rng.choice(parents),rng.choice(parents)
        child=tuple(rng.choice((x,y)) for x,y in zip(a,b)) if rng.random()<config.crossover else tuple(a)
        candidate=perturb(child,rng,config)
        if candidate==child or candidate in population:
            candidate=mutate_distinct(child,population,rng,config)
        population.append(candidate)
    return population


def fitness(standings,win_reward=3,attacker_weight=1.0,defender_weight=1.0):
    """Win-oriented fitness, optionally weighting attacker and defender games.

    Passing the full standings table with side weights >=0 keeps the official 2:1:0
    score untouched; it only changes which candidate the trainer prefers. A plain row
    and weights of 1.0 both reproduce the V2/V3/V4 formula exactly.
    """
    if win_reward not in (2,3,5):
        raise ValueError("A completed match suite and reward 2, 3 or 5 are required")
    if isinstance(standings,dict) and "attacker" in standings and "defender" in standings:
        numerator=denominator=0.0
        for key,weight in (("attacker",attacker_weight),("defender",defender_weight)):
            block=standings[key]
            if not weight or block["games"]<=0:
                continue
            numerator+=weight*(win_reward*block["wins"]+block["draws"])
            denominator+=weight*win_reward*block["games"]
        if denominator<=0:
            raise ValueError("Weighted games must be positive")
        return numerator/denominator
    if standings["games"]<=0:
        raise ValueError("A completed match suite and reward 2, 3 or 5 are required")
    return (win_reward*standings["wins"]+standings["draws"])/(win_reward*standings["games"])


def rank_key(trial):
    if not trial.get("eligible",True):
        return (-1.0,-1.0,-1.0)
    row=trial["standings"]["overall"]
    return trial["fitness"],row["wins"]/row["games"],-row["losses"]/row["games"]


def incumbent_weights(incumbent):
    """Accept either a champion trial/dict or a bare six-gene vector."""
    if incumbent is None:
        return None
    if isinstance(incumbent,dict):
        return tuple(incumbent["weights"])
    return tuple(incumbent)


def select_finalists(trials,config,incumbent=None):
    """Pick weight-unique finalists: baseline, incumbent, best new candidate, diversity.

    The baseline and the previous champion may coincide; then they share one slot and
    the freed slot goes to another distinct candidate. Never pads with duplicates.
    """
    eligible=[t for t in sorted(trials,key=rank_key,reverse=True) if t.get("eligible",True)]
    for position,trial in enumerate(eligible,1):
        trial.setdefault("quick_rank",position)
    champion_weights=incumbent_weights(incumbent)
    reference=champion_weights if champion_weights is not None else tuple(BASE_WEIGHTS)
    for trial in eligible:
        trial["distance_from_champion"]=round(weight_distance(trial["weights"],reference,config.bound),6)
    limit=min(config.finalists,config.population)
    selected,used=[],set()

    def add(trial,reason):
        genome=tuple(trial["weights"])
        if genome in used or len(selected)>=limit:
            return False
        used.add(genome)
        trial["selection_reason"]=reason
        selected.append(trial)
        return True

    baseline=next((t for t in eligible if tuple(t["weights"])==tuple(BASE_WEIGHTS)),None)
    if baseline is None:
        raise RuntimeError("Required manual baseline failed screening")
    add(baseline,"manual_baseline")
    reserved={tuple(BASE_WEIGHTS)}
    if champion_weights is not None:
        champion=next((t for t in eligible if tuple(t["weights"])==champion_weights),None)
        if champion is None:
            raise RuntimeError("Required incumbent champion failed screening")
        add(champion,"incumbent_champion")
        reserved.add(champion_weights)
    for trial in eligible:
        if len(selected)>=limit:
            break
        if tuple(trial["weights"]) in reserved:
            continue
        if add(trial,"best_new_candidate"):
            break
    for _ in range(config.diversity_slots):
        if len(selected)>=limit:
            break
        remaining=[t for t in eligible if tuple(t["weights"]) not in used]
        if not remaining:
            break
        # Quality gate first, distance second: the candidate must stay within
        # ``diversity_margin`` of the manual baseline's screening fitness and sit in
        # the upper half of the ranking, so an unqualified distant genome never wins
        # the slot (the V3 implementation only applied the positional window).
        window=remaining[:max(config.finalists+config.diversity_slots,(len(eligible)+1)//2)]
        threshold=baseline["fitness"]-config.diversity_margin
        pool=[t for t in window if t["fitness"]>=threshold]
        if not pool:
            break
        pick=max(pool,key=lambda t:(t["distance_from_champion"],rank_key(t)))
        if not add(pick,"diversity_candidate"):
            break
    for trial in eligible:
        if len(selected)>=limit:
            break
        add(trial,"quick_rank_fill")
    if len(selected)<limit:
        raise RuntimeError(f"Only {len(selected)} weight-unique eligible finalists; {limit} required")
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
