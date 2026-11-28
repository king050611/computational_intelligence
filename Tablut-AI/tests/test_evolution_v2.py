import json
from math import inf
from pathlib import Path
from random import Random
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from config.evolution import BASE_WEIGHTS,GENE_SIGNS,EvolutionConfig
from config.experimental import SearchOptions
from src.evolution import fitness,initial_population,next_population,select_finalists,opponent_schedule,rank_key
from src.evaluation import WeightedEvaluator
from src.game import initial_board,get_legal_moves,apply_move,check_winner
from src.enhanced_search import choose_enhanced,WIN_SCORE
from src.tactics import prioritize,TacticalInfo
from src.time_control import AdaptiveTimeManager
from scripts import train_evolution as train
from scripts.generate_openings import generate_openings
from scripts.benchmark import standings


def row(side='A',fault=None,owner='candidate'):
    issues={s:dict(illegal_moves=0,timeouts=0,exceptions=0,invalid_returns=[]) for s in ('A','D')}
    if fault:
        bad=side if owner=='candidate' else ('D' if side=='A' else 'A')
        issues[bad][fault]=['bad'] if fault=='invalid_returns' else 1
    return dict(our_side=side,winner='DRAW',attacker_seconds=.1,defender_seconds=.1,issues=issues)


def fake_runner(commands,fault=None,owner='candidate'):
    def run(command,**kwargs):
        commands.append(command)
        openings=json.loads(Path(command[command.index('--openings')+1]).read_text(encoding='utf-8'))['openings']
        rows=[row(side,fault,owner) for opening in openings for side in ('A','D')]
        payload=dict(games=len(rows),results=rows,standings=standings(rows))
        Path(command[command.index('--output')+1]).write_text(json.dumps(payload),encoding='utf-8')
        return SimpleNamespace(returncode=1 if fault else 0)
    return run


def setup(directory,config):
    for name,count,seed in [('quick_openings.json',config.quick_pairs,42),('selection_openings.json',config.final_pairs,43)]:
        (directory/name).write_text(json.dumps(generate_openings(count,seed)),encoding='utf-8')


class EvolutionV2Tests(unittest.TestCase):
    def test_win_rewards_separate_winning_from_drawing_and_keep_official_points(self):
        a=dict(games=10,wins=5,draws=0,losses=5)
        b=dict(games=10,wins=0,draws=10,losses=0)
        self.assertEqual(fitness(a,2),fitness(b,2))
        self.assertGreater(fitness(a,3),fitness(b,3))
        self.assertGreater(fitness(a,5),fitness(b,5))
        self.assertEqual(2*a['wins']+a['draws'],2*b['wins']+b['draws'])

    def test_sign_constraints_and_unconstrained_control_are_both_reproducible(self):
        for constrained in (True,False):
            config=EvolutionConfig(constrained=constrained,mutation=1)
            population=initial_population(config)
            self.assertEqual(population,initial_population(config))
            for generation in range(3):
                population=next_population(population[:4],config,generation)
                self.assertIn(BASE_WEIGHTS,population)
                self.assertTrue(all(abs(w)<=1000 for vector in population for w in vector))
                if constrained:self.assertTrue(all(w*sign>=0 for vector in population for w,sign in zip(vector,GENE_SIGNS)))
        self.assertTrue(any(vector[3]>0 or vector[4]<0 for vector in initial_population(EvolutionConfig(constrained=False))))

    def test_finalists_force_manual_control_and_incumbent_without_changing_size(self):
        config=EvolutionConfig()
        population=initial_population(config)
        trials=[dict(index=i,weights=w,fitness=i/8,eligible=True,standings={'overall':dict(games=4,wins=0,draws=4,losses=0)}) for i,w in enumerate(population)]
        selected=select_finalists(trials,config,population[1])
        self.assertEqual(len(selected),4)
        self.assertTrue({0,1}.issubset({t['index'] for t in selected}))
        trials[0]['eligible']=False
        with self.assertRaises(RuntimeError):select_finalists(trials,config)

    def test_pool_quota_rounding_and_first_generation_fallback(self):
        first=opponent_schedule(6,False,1)
        self.assertEqual(first.count('enhanced_dynamic'),4);self.assertEqual(first.count('enhanced'),2)
        later=opponent_schedule(8,True,2)
        self.assertEqual([later.count(n) for n in ('enhanced_dynamic','enhanced','historical')],[4,2,2])
        self.assertEqual(later,opponent_schedule(8,True,2))

    def test_two_stage_80_game_accounting_uses_same_schedule_for_every_candidate(self):
        commands=[];config=EvolutionConfig()
        with tempfile.TemporaryDirectory() as tmp,patch.object(train.subprocess,'run',side_effect=fake_runner(commands)):
            directory=Path(tmp);setup(directory,config)
            ranked,screen=train.run_generation(directory,initial_population(config),1,SearchOptions(),config=config)
            self.assertEqual(len(screen['quick_trials']),8);self.assertEqual(len(screen['final_trials']),4)
            self.assertEqual(sum(t['standings']['overall']['games'] for t in screen['quick_trials']),32)
            self.assertEqual(sum(t['standings']['overall']['games'] for t in screen['final_trials']),48)
            self.assertEqual(len(ranked),4)
            quick=[c for c in commands if c[c.index('--max-depth')+1]=='2']
            self.assertEqual(len(quick),16)
            self.assertEqual(len(commands),24)

    def test_previous_champion_is_rechecked_against_frozen_historical_pool(self):
        commands=[];config=EvolutionConfig();population=initial_population(config)
        incumbent=dict(weights=population[1],generation=1)
        with tempfile.TemporaryDirectory() as tmp,patch.object(train.subprocess,'run',side_effect=fake_runner(commands)):
            directory=Path(tmp);setup(directory,config)
            ranked,screen=train.run_generation(directory,population,2,SearchOptions(),config=config,incumbent=incumbent)
            self.assertIn('historical',screen['final_opponents'])
            self.assertTrue(any(tuple(t['weights'])==tuple(incumbent['weights']) for t in ranked))
            self.assertTrue(any('--opponent-model' in command for command in commands))

    def test_candidate_fault_disqualifies_without_retry_or_fitness(self):
        commands=[];config=EvolutionConfig()
        with tempfile.TemporaryDirectory() as tmp,patch.object(train.subprocess,'run',side_effect=fake_runner(commands,'exceptions')):
            directory=Path(tmp);setup(directory,config);attempt=directory/'attempt';attempt.mkdir()
            stage=train.prepare_stage(directory,attempt,'quick',SearchOptions(2),2,1,None)
            result=train.evaluate_candidate(directory,attempt,BASE_WEIGHTS,0,1,stage,config)
            self.assertFalse(result['eligible']);self.assertIsNone(result['fitness']);self.assertEqual(len(commands),1)

    def test_control_failure_retries_once_and_never_awards_fitness(self):
        commands=[];config=EvolutionConfig()
        with tempfile.TemporaryDirectory() as tmp,patch.object(train.subprocess,'run',side_effect=fake_runner(commands,'timeouts','control')):
            directory=Path(tmp);setup(directory,config);attempt=directory/'attempt';attempt.mkdir()
            stage=train.prepare_stage(directory,attempt,'quick',SearchOptions(2),2,1,None)
            with self.assertRaises(RuntimeError):train.evaluate_candidate(directory,attempt,BASE_WEIGHTS,0,1,stage,config)
            self.assertEqual(len(commands),2)

    def test_wall_clock_violation_is_rejected_even_without_referee_error(self):
        record=row();record['attacker_seconds']=60.001
        self.assertEqual(train.classify_rows([record]),'candidate_fault')
        record=row();record['defender_seconds']=60.001
        self.assertEqual(train.classify_rows([record]),'control_fault')

    def test_tactical_order_preserves_moves_and_deadline_unknown_does_not_filter(self):
        board=initial_board();moves=get_legal_moves(board,'A')
        with patch('src.tactics.perf_counter',return_value=5):
            ordered,info=prioritize(board,'A',moves,5)
        self.assertFalse(info.status_complete);self.assertEqual(ordered,moves)
        self.assertEqual(set(ordered),set(moves))

    def test_exact_terminal_wins_override_hostile_but_valid_weights(self):
        board=[['.']*9 for _ in range(9)];board[4][4]='X';board[2][2]='K';board[2][1]='A';board[2][6]='A';board=tuple(map(tuple,board))
        for side in ('A','D'):
            stats={};move=choose_enhanced(board,side,deadline=inf,evaluator=WeightedEvaluator((10000,)*8),stats=stats)
            self.assertEqual(check_winner(apply_move(board,move,side),'D' if side=='A' else 'A'),side)
            self.assertGreaterEqual(stats['score'],WIN_SCORE-1)

    def test_tactical_budget_cap_and_zero_game_budget(self):
        board=initial_board();moves=get_legal_moves(board,'A')
        info=TacticalInfo((),None,(),False,'unknown')
        with patch('src.enhanced_search.perf_counter',return_value=100),patch('src.enhanced_search.is_urgent',return_value=True),patch('src.enhanced_search.prioritize',return_value=(moves,info)) as diagnostic:
            choose_enhanced(board,'A',deadline=101,options=SearchOptions(1))
            self.assertLessEqual(diagnostic.call_args.args[3],100.01)
        clock=AdaptiveTimeManager();clock.record_elapsed(55)
        self.assertEqual(clock.deadlines(10),(10,10))
        with patch('src.enhanced_search.prioritize',side_effect=AssertionError('No diagnostic budget')):
            self.assertIn(choose_enhanced(board,'A',deadline=0),moves)
