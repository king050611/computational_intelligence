"""V5-C: attacker-weighted training fitness.

The official 2:1:0 score stays untouched; only the trainer's preference changes.
"""
import unittest

from config.evolution import EvolutionConfig
from scripts import train_evolution as train
from src.evolution import fitness, rank_key


def table(aw, ad, al, dw, dd, dl):
    attacker = dict(games=aw + ad + al, wins=aw, draws=ad, losses=al, points=2 * aw + ad)
    defender = dict(games=dw + dd + dl, wins=dw, draws=dd, losses=dl, points=2 * dw + dd)
    overall = dict(games=attacker["games"] + defender["games"],
                   wins=aw + dw, draws=ad + dd, losses=al + dl, points=attacker["points"] + defender["points"])
    return dict(overall=overall, attacker=attacker, defender=defender)


class SideWeightedFitnessTests(unittest.TestCase):
    def test_unit_weights_reproduce_the_plain_formula(self):
        data = table(5, 2, 3, 1, 6, 3)
        self.assertAlmostEqual(fitness(data, 3), fitness(data["overall"], 3))
        self.assertAlmostEqual(fitness(data, 3, 1.0, 1.0), fitness(data["overall"], 3))

    def test_attacker_games_can_be_weighted_more(self):
        # We win as defender but lose as attacker; up-weighting attacker games must hurt.
        data = table(0, 0, 10, 10, 0, 0)
        plain = fitness(data, 3)
        attacker_heavy = fitness(data, 3, 3.0, 1.0)
        defender_heavy = fitness(data, 3, 1.0, 3.0)
        self.assertAlmostEqual(plain, 0.5)
        self.assertLess(attacker_heavy, plain)
        self.assertGreater(defender_heavy, plain)

    def test_weighted_fitness_keeps_official_points_independent(self):
        data = table(6, 0, 4, 2, 4, 4)
        self.assertEqual(data["overall"]["points"], 2 * 8 + 4)
        self.assertNotEqual(fitness(data, 3, 2.0, 1.0), fitness(data, 3))

    def test_zero_weighted_sides_are_rejected(self):
        with self.assertRaises(ValueError):
            EvolutionConfig(attacker_game_weight=0.0, defender_game_weight=0.0)
        with self.assertRaises(ValueError):
            EvolutionConfig(attacker_game_weight=-1.0)
        with self.assertRaises(ValueError):
            EvolutionConfig(attacker_game_weight=float("nan"))

    def test_zero_weight_on_an_empty_side_is_ignored(self):
        data = dict(overall=dict(games=6, wins=3, draws=3, losses=0, points=9),
                    attacker=dict(games=6, wins=3, draws=3, losses=0, points=9),
                    defender=dict(games=0, wins=0, draws=0, losses=0, points=0))
        self.assertAlmostEqual(fitness(data, 3, 1.0, 5.0), 12 / 18)

    def test_ranking_uses_the_weighted_fitness(self):
        weak_attacker = dict(fitness=fitness(table(0, 0, 10, 10, 0, 0), 3, 3.0, 1.0),
                             standings=table(0, 0, 10, 10, 0, 0), eligible=True)
        balanced = dict(fitness=fitness(table(5, 0, 5, 5, 0, 5), 3, 3.0, 1.0),
                        standings=table(5, 0, 5, 5, 0, 5), eligible=True)
        ranked = sorted([weak_attacker, balanced], key=rank_key, reverse=True)
        self.assertGreater(ranked[0]["fitness"], ranked[1]["fitness"])

    def test_trial_statistics_records_the_weighted_value(self):
        rows = []
        for side, winner in (("A", "D"), ("A", "D"), ("D", "D")):
            rows.append(dict(our_side=side, winner=winner, attacker_seconds=1.0, defender_seconds=1.0,
                             our_mean_move_seconds=0.1,
                             issues={s: dict(illegal_moves=0, timeouts=0, exceptions=0, invalid_returns=[])
                                     for s in ("A", "D")}))
        weighted = train.trial_statistics(rows, 3, attacker_weight=3.0, defender_weight=1.0)
        plain = train.trial_statistics(rows, 3)
        self.assertLess(weighted["overall"]["training_fitness"], plain["overall"]["training_fitness"])
        self.assertEqual(weighted["overall"]["points"], plain["overall"]["points"])


if __name__ == "__main__":
    unittest.main()
