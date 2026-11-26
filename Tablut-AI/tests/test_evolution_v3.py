"""V3 training-mechanism tests: weight-unique populations, finalist slots, warm start."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from config.evolution import BASE_WEIGHTS, EvolutionConfig
from config.experimental import SearchOptions
from scripts import train_evolution as train
from scripts.benchmark import standings
from scripts.generate_openings import generate_openings
from src.evaluation import WeightedEvaluator, model_record
from src.evolution import (deduplicate, initial_population, mutate_distinct, next_population,
                           population_report, select_finalists, weight_distance)


def trial(index, weights, fitness, games=8, wins=None, draws=None):
    draws = games if draws is None else draws
    wins = 0 if wins is None else wins
    row = dict(games=games, wins=wins, draws=draws, losses=games - wins - draws)
    return dict(index=index, weights=tuple(float(w) for w in weights), fitness=fitness, eligible=True,
                points=2 * wins + draws, standings=dict(overall=row, attacker=row, defender=row))


def result_row(side="A", games=1, our_mean_move_seconds=0.5, depth=3, seconds=20.0):
    return dict(our_side=side, winner="DRAW", attacker_seconds=seconds, defender_seconds=seconds,
                our_mean_move_seconds=our_mean_move_seconds,
                issues={s: dict(illegal_moves=0, timeouts=0, exceptions=0, invalid_returns=[]) for s in ("A", "D")},
                search_stats={s: [dict(completed_depth=depth)] if s == side else [] for s in ("A", "D")})


def fake_runner(commands, fault=None):
    def run(command, **kwargs):
        commands.append(command)
        openings = json.loads(Path(command[command.index("--openings") + 1]).read_text(encoding="utf-8"))["openings"]
        rows = [result_row(side) for opening in openings for side in ("A", "D")]
        payload = dict(games=len(rows), results=rows, standings=standings(rows))
        Path(command[command.index("--output") + 1]).write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=1 if fault else 0)
    return run


def setup_openings(directory, config):
    for name, count, seed in (("quick_openings.json", config.quick_pairs, 42),
                              ("selection_openings.json", config.final_pairs, 43)):
        (directory / name).write_text(json.dumps(generate_openings(count, seed)), encoding="utf-8")


class PopulationDedupTests(unittest.TestCase):
    def test_initial_population_is_weight_unique(self):
        config = EvolutionConfig()
        population = initial_population(config)
        self.assertEqual(len(population), config.population)
        self.assertEqual(len(set(population)), config.population)
        self.assertEqual(population[0], tuple(BASE_WEIGHTS))
        self.assertEqual(population, initial_population(config))

    def test_initial_population_keeps_baseline_and_warm_start_champion(self):
        config = EvolutionConfig()
        champion = (-373.41453247458276, 578.6130017202265, -177.3566947316156, 0.0, 18.58381895253767, 0.0)
        population = initial_population(config, seed_weights=champion)
        self.assertIn(tuple(BASE_WEIGHTS), population)
        self.assertIn(tuple(champion), population)
        self.assertEqual(len(set(population)), config.population)

    def test_identical_warm_start_champion_is_not_duplicated(self):
        config = EvolutionConfig()
        population = initial_population(config, seed_weights=BASE_WEIGHTS)
        self.assertEqual(len(set(population)), config.population)
        self.assertEqual(population.count(tuple(BASE_WEIGHTS)), 1)

    def test_next_population_stays_unique_across_generations(self):
        config = EvolutionConfig()
        population = initial_population(config)
        champion = population[1]
        for generation in range(1, 5):
            ranked = list(reversed(population[: config.finalists]))
            population = next_population(ranked, config, generation, incumbent=champion)
            self.assertEqual(len(population), config.population)
            self.assertEqual(len(set(population)), config.population)
            self.assertIn(tuple(BASE_WEIGHTS), population)
            self.assertIn(tuple(champion), population)

    def test_zero_mutation_still_produces_unique_offspring(self):
        config = EvolutionConfig(population=6, elite=2, mutation=0.0, crossover=0.0)
        population = initial_population(config)
        evolved = next_population(population[:4], config, 1)
        self.assertEqual(len(set(evolved)), 6)
        self.assertEqual(evolved[:2], population[:2])

    def test_constrained_projection_keeps_dedup_valid(self):
        config = EvolutionConfig(constrained=True, mutation=1.0, sigma=5.0)
        population = initial_population(config)
        for generation in range(1, 4):
            population = next_population(population[:4], config, generation)
            self.assertEqual(len(set(population)), config.population)
            for genome in population:
                self.assertTrue(all(w * sign >= 0 for w, sign in zip(genome, (-1, 1, -1, -1, 1, -1))))

    def test_runaway_duplicates_raise_instead_of_looping(self):
        config = EvolutionConfig(population=6, elite=2, dedup_attempts=3)
        population = initial_population(config)
        with patch("src.evolution.perturb", return_value=tuple(BASE_WEIGHTS)), \
                patch("src.evolution.mutate_distinct", side_effect=RuntimeError("no distinct mutant")):
            with self.assertRaises(RuntimeError):
                next_population(population[:4], config, 1)

    def test_mutate_distinct_changes_at_least_one_gene(self):
        config = EvolutionConfig()
        population = initial_population(config)
        from random import Random
        candidate = mutate_distinct(population[0], population, Random(7), config)
        self.assertNotEqual(candidate, population[0])
        self.assertNotIn(candidate, population)

    def test_population_report_counts_duplicates(self):
        report = population_report([(1.0,) * 6, (1.0,) * 6, (2.0,) * 6])
        self.assertEqual(report, dict(size=3, distinct=2, duplicates=1))
        self.assertEqual(deduplicate([(1.0,) * 6, (1.0,) * 6, (2.0,) * 6]), [(1.0,) * 6, (2.0,) * 6])


class FinalistSelectionTests(unittest.TestCase):
    def test_baseline_and_champion_share_one_slot(self):
        config = EvolutionConfig()
        population = initial_population(config)
        trials = [trial(i, w, i / 8) for i, w in enumerate(population)]
        selected = select_finalists(trials, config, BASE_WEIGHTS)
        self.assertEqual(len(selected), 4)
        genomes = [tuple(t["weights"]) for t in selected]
        self.assertEqual(len(set(genomes)), 4)
        self.assertEqual(genomes.count(tuple(BASE_WEIGHTS)), 1)
        self.assertEqual(selected[0]["selection_reason"], "manual_baseline")

    def test_distinct_champion_occupies_its_own_slot(self):
        config = EvolutionConfig()
        population = initial_population(config)
        champion = population[1]
        trials = [trial(i, w, i / 8) for i, w in enumerate(population)]
        selected = select_finalists(trials, config, champion)
        reasons = {t["selection_reason"] for t in selected}
        self.assertEqual(len({tuple(t["weights"]) for t in selected}), 4)
        self.assertIn("manual_baseline", reasons)
        self.assertIn("incumbent_champion", reasons)
        self.assertIn("best_new_candidate", reasons)

    def test_insufficient_distinct_candidates_aborts(self):
        config = EvolutionConfig(population=4, elite=2, finalists=4)
        trials = [trial(0, BASE_WEIGHTS, 0.5), trial(1, BASE_WEIGHTS, 0.4),
                  trial(2, (-300.0, 500.0, -100.0, 0.0, 0.0, 0.0), 0.3),
                  trial(3, (-300.0, 500.0, -100.0, 0.0, 0.0, 0.0), 0.2)]
        with self.assertRaises(RuntimeError):
            select_finalists(trials, config)

    def test_diversity_slot_prefers_qualified_distant_candidate(self):
        config = EvolutionConfig()
        base = tuple(BASE_WEIGHTS)
        qualifying = (-100.0, 300.0, -60.0, 0.0, 0.0, 0.0)
        distant = (-1000.0, 1000.0, -1000.0, 0.0, 0.0, 0.0)
        near = [(-390.0, 590.0, -158.0, 0.0, 0.0, 0.0),
                (-380.0, 580.0, -150.0, 0.0, 0.0, 0.0),
                (-370.0, 570.0, -140.0, 0.0, 0.0, 0.0),
                (-360.0, 560.0, -130.0, 0.0, 0.0, 0.0)]
        weights = [base, (-200.0, 400.0, -100.0, 0.0, 0.0, 0.0), qualifying] + near + [distant]
        trials = [trial(i, w, 1.0 - i / 10) for i, w in enumerate(weights)]
        selected = select_finalists(trials, config)
        diversity = [t for t in selected if t["selection_reason"] == "diversity_candidate"]
        self.assertTrue(diversity)
        chosen = {tuple(t["weights"]) for t in selected}
        self.assertIn(tuple(qualifying), chosen)
        self.assertNotIn(tuple(distant), chosen)
        self.assertGreater(weight_distance(qualifying, base, config.bound), 0.3)
        self.assertLess(weight_distance(qualifying, base, config.bound),
                        weight_distance(distant, base, config.bound))

    def test_weight_distance_is_normalized_by_bound(self):
        base = tuple(BASE_WEIGHTS)
        shifted = tuple(w + (1000.0 if i == 0 else 0.0) for i, w in enumerate(base))
        self.assertAlmostEqual(weight_distance(shifted, base, 1000.0), 1.0)
        self.assertAlmostEqual(weight_distance(base, base, 1000.0), 0.0)
        with self.assertRaises(ValueError):
            weight_distance(base, base[:5], 1000.0)
        with self.assertRaises(ValueError):
            weight_distance(base, base, 0)


class WarmStartTests(unittest.TestCase):
    def test_initial_model_is_loaded_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "best.json"
            path.write_text(json.dumps(model_record(BASE_WEIGHTS, generation=1)), encoding="utf-8")
            args = argparse.Namespace(initial_model=path, initial_checkpoint=None)
            weights, source = train.load_initial_weights(args, EvolutionConfig())
            self.assertEqual(tuple(weights), tuple(BASE_WEIGHTS))
            self.assertEqual(source["kind"], "model")
            self.assertEqual(len(source["sha256"]), 64)

    def test_initial_checkpoint_reports_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint-0001.json"
            champion = [-373.0, 578.0, -177.0, 0.0, 18.0, 0.0]
            path.write_text(json.dumps(dict(schema_version=2, generation=1, best=dict(weights=champion, generation=1, fitness=0.6, points=16))), encoding="utf-8")
            args = argparse.Namespace(initial_model=None, initial_checkpoint=path)
            weights, source = train.load_initial_weights(args, EvolutionConfig())
            self.assertEqual(tuple(weights), tuple(champion))
            self.assertEqual(source["generation"], 1)
            self.assertEqual(source["kind"], "checkpoint")

    def test_invalid_initial_weights_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            args = argparse.Namespace(initial_model=path, initial_checkpoint=None)
            path.write_text(json.dumps(model_record((100.0, 600.0, -160.0, 0.0, 0.0, 0.0))), encoding="utf-8")
            with self.assertRaises(ValueError):
                train.load_initial_weights(args, EvolutionConfig(constrained=True))
            self.assertEqual(train.load_initial_weights(args, EvolutionConfig(constrained=False))[0][0], 100.0)
            path.write_text(json.dumps(dict(schema_version=1, model_type="evolutionary_dynamic",
                                            features=["king_pressure", "escape_routes", "weighted_material",
                                                      "edge_distance", "king_mobility", "escape_blockade"],
                                            weights=[float("nan")] * 6)), encoding="utf-8")
            with self.assertRaises(ValueError):
                train.load_initial_weights(args, EvolutionConfig())
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                train.load_initial_weights(args, EvolutionConfig())

    def test_checkpoint_without_champion_weights_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint-0000.json"
            path.write_text(json.dumps(dict(schema_version=2, generation=0, best=None)), encoding="utf-8")
            args = argparse.Namespace(initial_model=None, initial_checkpoint=path)
            with self.assertRaises(ValueError):
                train.load_initial_weights(args, EvolutionConfig())


class TrainingPipelineTests(unittest.TestCase):
    def test_trial_statistics_reports_attacker_defender_and_depth(self):
        rows = [result_row("A", our_mean_move_seconds=0.4, depth=3),
                result_row("D", our_mean_move_seconds=0.6, depth=4)]
        stats = train.trial_statistics(rows, 3)
        self.assertEqual(stats["overall"]["games"], 2)
        self.assertEqual(stats["attacker"]["games"], 1)
        self.assertEqual(stats["defender"]["games"], 1)
        self.assertAlmostEqual(stats["mean_move_seconds"], 0.5)
        self.assertAlmostEqual(stats["mean_completed_depth"], 3.5)
        self.assertEqual(stats["recorded_depths"], 2)
        self.assertIn("official_rate", stats["overall"])

    def test_run_generation_records_weight_unique_selection(self):
        config = EvolutionConfig()
        commands = []
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(train.subprocess, "run", side_effect=fake_runner(commands)):
            directory = Path(tmp)
            setup_openings(directory, config)
            ranked, screening = train.run_generation(directory, initial_population(config), 1,
                                                     SearchOptions(), config=config)
            selection = screening["finalist_selection"]
            self.assertEqual(len(selection), 4)
            self.assertEqual(len({tuple(item["weights"]) for item in selection}), 4)
            self.assertEqual(selection[0]["selection_reason"], "manual_baseline")
            self.assertTrue(all(item["quick_rank"] for item in selection))
            self.assertTrue(all(item["distance_from_champion"] is not None for item in selection))
            self.assertEqual(len(ranked), 4)

    def test_warm_start_main_writes_provenance_and_unique_population(self):
        def fake_generation(directory, population, generation, options, seed=42, **kwargs):
            ranked = [dict(weights=w, fitness=(len(population) - i) / 10, points=len(population) - i,
                           eligible=True, standings=dict(overall=dict(games=1, wins=0, draws=1, losses=0),
                                                         attacker=dict(games=1, wins=0, draws=1, losses=0),
                                                         defender=dict(games=1, wins=0, draws=1, losses=0)))
                      for i, w in enumerate(population[:4])]
            return ranked, dict(finalist_selection=[])
        with tempfile.TemporaryDirectory() as tmp:
            champion = (-373.0, 578.0, -177.0, 0.0, 18.0, 0.0)
            model = Path(tmp) / "v2_champion.json"
            model.write_text(json.dumps(model_record(champion, generation=1)), encoding="utf-8")
            directory = Path(tmp) / "run"
            with patch.object(train, "run_generation", side_effect=fake_generation), \
                    contextlib.redirect_stdout(io.StringIO()):
                train.main(["--output-dir", str(directory), "--generations", "1", "--population", "4",
                            "--elite", "2", "--finalists", "2", "--pairs", "1", "--quick-pairs", "1",
                            "--quick-depth", "1", "--max-depth", "1", "--initial-model", str(model)])
            checkpoint = json.loads((directory / "checkpoint-0000.json").read_text(encoding="utf-8"))
            self.assertEqual(tuple(checkpoint["initial_weights"]), tuple(champion))
            self.assertEqual(checkpoint["initial_weights_source"]["kind"], "model")
            self.assertEqual(checkpoint["population_stats"]["distinct"], 4)
            self.assertIn(tuple(BASE_WEIGHTS), [tuple(w) for w in checkpoint["population"]])
            self.assertIn(tuple(champion), [tuple(w) for w in checkpoint["population"]])
            final = json.loads(sorted(directory.glob("checkpoint-*.json"))[-1].read_text(encoding="utf-8"))
            self.assertEqual(final["generation"], 1)
            self.assertEqual(final["population_stats"]["distinct"], 4)
            self.assertTrue(final["population_retention"]["baseline_present"])
            self.assertTrue((directory / "best.json").exists())

    def test_resume_rejects_reseeding(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "run"
            with patch.object(train, "run_generation", side_effect=RuntimeError("stop")), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    train.main(["--output-dir", str(directory), "--generations", "1", "--population", "2",
                                "--elite", "1", "--finalists", "2", "--pairs", "1", "--max-depth", "1"])
            model = Path(tmp) / "m.json"
            model.write_text(json.dumps(model_record(BASE_WEIGHTS)), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                train.main(["--output-dir", str(directory), "--resume", "--generations", "1",
                            "--initial-model", str(model)])

    def test_source_hash_change_blocks_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "run"
            with patch.object(train, "run_generation", side_effect=RuntimeError("stop")), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    train.main(["--output-dir", str(directory), "--generations", "1", "--population", "2",
                                "--elite", "1", "--finalists", "2", "--pairs", "1", "--max-depth", "1"])
            with patch.object(train, "source_hash", return_value="0" * 64), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                train.main(["--output-dir", str(directory), "--resume", "--generations", "1"])

    def test_invalid_hyperparameters_are_rejected(self):
        for kwargs in (dict(dedup_attempts=0), dict(diversity_slots=-1), dict(diversity_slots=9)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                EvolutionConfig(**kwargs)


if __name__ == "__main__":
    unittest.main()
