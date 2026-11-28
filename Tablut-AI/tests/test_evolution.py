import contextlib
import io
import json
from math import inf
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from config.evolution import BASE_WEIGHTS,EvolutionConfig
from config.experimental import SearchOptions,STRATEGIES
from scripts import benchmark,train_evolution,play_cli,replay_demo
from src.evaluation import WeightedEvaluator,evaluate_defender,load_evaluator,model_record
from src.features import extract_features,FEATURE_NAMES
from src.game import initial_board,apply_move,get_legal_moves,get_state_key
from src.evolution import initial_population,next_population
from src.enhanced_search import choose_enhanced
from src.experimental_player import ExperimentalPlayer
from src.time_control import AdaptiveTimeManager
from TeamXX import LegacyPlayer as Player

class EvolutionTests(unittest.TestCase):
    def test_features_baseline_equivalence_and_perspective(self):
        board=initial_board();model=WeightedEvaluator(BASE_WEIGHTS)
        for ply in range(20):
            self.assertEqual(len(extract_features(board)),len(FEATURE_NAMES))
            self.assertEqual(model(board,"D"),evaluate_defender(board))
            self.assertEqual(model(board,"A"),-model(board,"D"))
            side="A" if ply%2==0 else "D";moves=get_legal_moves(board,side)
            board=apply_move(board,moves[ply%len(moves)],side)

    def test_blockade_distinguishes_blocker_distance(self):
        def features(col):
            b=[["."]*9 for _ in range(9)];b[4][4]="K";b[4][col]="A";b[0][0]="A"
            return extract_features(tuple(map(tuple,b)))
        near,far=features(6),features(7)
        self.assertEqual(near[1],far[1]);self.assertGreater(near[5],far[5]);self.assertLess(near[4],far[4])

    def test_models_roundtrip_and_legacy_invalid_weights_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"model.json";p.write_text(json.dumps(model_record(BASE_WEIGHTS)))
            self.assertEqual(load_evaluator(p).weights,BASE_WEIGHTS)
            for record in ({"schema_version":1,"best":{"weights":[1,2,3,4]}},dict(model_record(BASE_WEIGHTS),features=list(reversed(FEATURE_NAMES)))):
                p.write_text(json.dumps(record))
                with self.assertRaises(ValueError):load_evaluator(p)
            for w in ([1]*7,[True]*8,[float("nan")]*8,[10001]*8):
                with self.assertRaises(ValueError):WeightedEvaluator(tuple(w))

    def test_shared_search_timing_and_formal_default(self):
        board=initial_board();options=SearchOptions(2)
        self.assertEqual(choose_enhanced(board,"A",deadline=inf,options=options),choose_enhanced(board,"A",deadline=inf,options=options,evaluator=WeightedEvaluator(BASE_WEIGHTS)))
        for strategy in STRATEGIES:
            evaluator=WeightedEvaluator(BASE_WEIGHTS) if strategy=="evolutionary_dynamic" else None
            bot=ExperimentalPlayer(strategy,evaluator=evaluator,record_search=True)
            bot.clock.record_elapsed(60);original=[list(row) for row in board]
            move=bot.play_attacker(original)
            self.assertIn(tuple(map(tuple,move)),get_legal_moves(board,"A"))
            self.assertEqual(bot.last_search_stats["completed_depth"],0)
            self.assertEqual(original,[list(row) for row in board])
            self.assertIn(get_state_key(board,"A"),bot.history)
        self.assertEqual(Player().strategy,"enhanced_dynamic");self.assertIsNone(Player().evaluator)
        self.assertIsInstance(ExperimentalPlayer("evolutionary_dynamic",evaluator=WeightedEvaluator(BASE_WEIGHTS)).clock,AdaptiveTimeManager)

    def test_genetics_elites_reproducible_bounded_mutation(self):
        config=EvolutionConfig(population=6,elite=2,mutation=1,bound=600)
        population=initial_population(config);self.assertEqual(population,initial_population(config))
        evolved=next_population(population,config,1)
        self.assertEqual(evolved[:2],population[:2]);self.assertEqual(evolved,next_population(population,config,1))
        self.assertEqual(len(evolved),6);self.assertTrue(all(abs(w)<=600 for genome in evolved for w in genome));self.assertNotEqual(evolved[2:],population[2:])
        for kw in ({"elite":12},{"population":1},{"mutation":1.1},{"crossover":float("nan")}):
            with self.assertRaises(ValueError):EvolutionConfig(**kw)

    def test_removed_strategies_and_invalid_model_combinations(self):
        cases=[['--strategy','adaptive'],['--strategy','minimax'],['--neural-model','old.npz'],['--strategy','evolutionary_dynamic'],['--model','old.json'],['--opponent','evolutionary_dynamic']]
        for args in cases:
            with patch('sys.argv',['benchmark.py',*args]),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as exc:benchmark.main()
            self.assertEqual(exc.exception.code,2)
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):play_cli.main(['--side','A','--strategy','evolutionary_dynamic'])
        with patch('sys.argv',['replay_demo.py','--strategy','evolutionary_dynamic']),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):replay_demo.main()

    def test_resume_stop_and_suite_tampering(self):
        def fitness(directory,population,generation,options,seed,**kwargs):
            return ([dict(weights=w,points=len(population)-i,fitness=1-i/len(population),eligible=True) for i,w in enumerate(population)],{})
        with tempfile.TemporaryDirectory() as tmp,patch.object(train_evolution,'run_generation',side_effect=fitness),contextlib.redirect_stdout(io.StringIO()):
            directory=Path(tmp)/'run';args=['--output-dir',str(directory)]
            train_evolution.main(args+['--generations','1','--population','2','--elite','1','--pairs','1','--quick-depth','1','--max-depth','1'])
            expected=load_evaluator(directory/'best.json').weights
            (directory/'g0002_partial').mkdir()
            train_evolution.main(args+['--resume','--generations','1'])
            self.assertTrue((directory/'checkpoint-0002.json').exists());self.assertEqual(load_evaluator(directory/'best.json').weights,expected)
            (directory/'STOP').touch();train_evolution.main(args+['--resume','--generations','1'])
            self.assertFalse((directory/'checkpoint-0003.json').exists())
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):train_evolution.main(args+['--resume','--pairs','2'])
            p=directory/'selection_openings.json';p.write_text(p.read_text()+' ')
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):train_evolution.main(args+['--resume'])

    def test_failed_fitness_never_promotes_or_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(train_evolution,'run_generation',side_effect=RuntimeError('illegal game')),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            directory=Path(tmp)/'run'
            with self.assertRaises(SystemExit):train_evolution.main(['--output-dir',str(directory),'--generations','1','--population','2','--elite','1','--pairs','1'])
            self.assertTrue((directory/'checkpoint-0000.json').exists());self.assertFalse((directory/'checkpoint-0001.json').exists());self.assertFalse((directory/'best.json').exists())


    def test_defender_adapter_seeds_initial_attacker_history(self):
        board=initial_board();move=get_legal_moves(board,"A")[0]
        after=apply_move(board,move,"A")
        formal=Player();formal.clock.record_elapsed(60)
        formal.play_defender(after)
        self.assertEqual(formal.history[0],get_state_key(board,"A"))
        self.assertIn(get_state_key(after,"D"),formal.history)
