"""Final benchmark protocol: central control, mistake feedback/penalties, weights, judges."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import contextlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark
import experiment
import judge_agreement
import maci_judge
from policy import CentralCodePolicy
from scoring import ScoreConfig, score_episode
from sequence_rooms import build_sequence_rooms
from tests.test_blind_code import enter
from token_usage import tracker

CENTRAL_CODE = '''def decide(observation):
    if "team" not in observation:
        return {"type": "noop"}
    angle = 10 if observation["agent_id"] == "A" else -10
    return {"type": "turn", "angle": angle, "recheck_after": 50}
'''


class FeedbackAndPenaltyTests(unittest.TestCase):
    def test_unknown_action_is_invalid_reported_and_capped(self):
        env, _, objectives = build_sequence_rooms(seed=3)
        self.assertEqual(env.apply_action('A', {'type': 'wait'}), {'type': 'noop'})
        result = env.get_observation('A')['last_action_result']
        self.assertEqual(result['status'], 'invalid')
        self.assertIn("unknown action type 'wait'", result['reason'])
        for _ in range(14):
            env.apply_action('A', {'type': 'send_message', 'receiver_id': 'Z', 'content': 'hi'})
        self.assertIn('unknown receiver_id', env.get_observation('A')['last_action_result']['reason'])
        score = score_episode(env, 80, objectives)
        self.assertEqual(score['agents']['A']['invalid_actions'], 15)
        self.assertEqual(score['agents']['A']['score'], ScoreConfig().invalid_action_penalty_cap)
        self.assertEqual(score['agents']['B']['score'], 0)

    def test_no_effect_interaction_is_reported_and_penalized_individually(self):
        env, _, objectives = build_sequence_rooms(seed=3)
        env.step_count = 1
        final = env.apply_action('B', {'type': 'pick_up', 'object_id': 'missing'})
        env.decision_log.record(1, 'B', {}, final, final)
        self.assertEqual(env.get_observation('B')['last_action_result']['status'], 'no_effect')
        env.apply_action('A', {'type': 'turn', 'angle': 5})
        self.assertEqual(env.get_observation('A')['last_action_result']['status'], 'ok')
        score = score_episode(env, 80, objectives)
        self.assertEqual(score['agents']['B']['score'], ScoreConfig().failed_attempt_penalty)
        self.assertEqual(score['team']['failed_attempts'], 1)
        self.assertEqual(score['team']['score'], 0)

    def test_reset_notifies_both_agents_with_cause(self):
        env, _, _ = build_sequence_rooms(seed=3)
        wrong = next(p for p, o in env.objects.items() if o['type'] == 'number_pad'
                     and o['room'] == 'A' and p != env.sequence[0])
        enter(env, 'A', wrong)
        notices = {aid: env.get_observation(aid)['notices'] for aid in env.agents}
        self.assertEqual(notices['A'][-1]['type'], 'sequence_reset')
        self.assertTrue(notices['A'][-1]['caused_by_you'])
        self.assertFalse(notices['B'][-1]['caused_by_you'])

    def test_cross_room_handoff_earns_cooperation_points(self):
        env, _, objectives = build_sequence_rooms(seed=3)
        rooms = [env.objects[p]['room'] for p in env.sequence]
        switch = next(i for i in range(1, len(rooms)) if rooms[i] != rooms[i - 1])
        for pad in env.sequence[:switch + 1]:
            env.press_number_pad(env.objects[pad]['room'], pad, contact=True)
        receiver = rooms[switch]
        reasons = [item['reason'] for item in score_episode(env, 80, objectives)['agents'][receiver]['items']]
        self.assertIn('순서 이어받기', reasons)

    def test_score_config_file_roundtrip_and_unknown_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'w.json'
            path.write_text(json.dumps({'clear_bonus': 99}), encoding='utf-8')
            self.assertEqual(benchmark.load_score_config(str(path)).clear_bonus, 99)
            path.write_text(json.dumps({'nonsense': 1}), encoding='utf-8')
            with self.assertRaises(ValueError):
                benchmark.load_score_config(str(path))
        shipped = json.loads((Path(benchmark.HERE) / 'scoring_weights.json').read_text(encoding='utf-8'))
        self.assertEqual(ScoreConfig.from_dict(shipped), ScoreConfig())


class CentralControllerTests(unittest.TestCase):
    def test_one_code_controls_every_agent_with_team_observations(self):
        env, tasks, _ = build_sequence_rooms(seed=3)
        central = CentralCodePolicy('test', benchmark.central_task_description(tasks), list(env.agents))
        for agent in env.agents.values():
            agent.set_policy(central)
        env.joint_policy = central
        before = {aid: a.facing for aid, a in env.agents.items()}
        with patch.object(central, '_generate_code', return_value=CENTRAL_CODE) as generate:
            env.step()
            env.step()
        self.assertEqual(generate.call_count, 1)
        self.assertIn('Current observations by agent', generate.call_args.args[0])
        self.assertAlmostEqual(env.agents['A'].facing, (before['A'] + 20) % 360)
        self.assertAlmostEqual(env.agents['B'].facing, (before['B'] - 20) % 360)
        self.assertEqual(central.code_checks.snapshot()['execution_successes'], 4)
        self.assertEqual(sum('Simulation step result' in m['content'] for m in central.conversation_history), 2)
        self.assertIn('[Agent A]', central.task_description)

    def test_central_run_shares_tokens_and_records_condition(self):
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=120_000, total_tokens=121_000)

        def fake_generate(policy, *args, **kwargs):
            tracker(policy.client).record(SimpleNamespace(usage=usage))
            return CENTRAL_CODE
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()), \
                patch.object(CentralCodePolicy, '_generate_code', autospec=True, side_effect=fake_generate):
            path = Path(folder) / 'central.jsonl'
            benchmark.run_episode('test', 'https://example.test/v1', 'key', {}, 3, str(path),
                                  environment_kind='sequence_rooms', sequence_seed=3, controller='central')
            records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            score = json.loads(path.with_suffix('.score.json').read_text(encoding='utf-8'))
        self.assertEqual({r['controller'] for r in records}, {'central'})
        self.assertEqual(score['controller'], 'central')
        self.assertEqual(score['score_config'], ScoreConfig().to_dict())
        # One model controls two agents: double allowance, penalty split equally.
        self.assertEqual(score['agents']['A']['token_penalty'], -10.0)
        self.assertEqual(score['agents']['B']['token_penalty'], -10.0)
        self.assertEqual(score['agents']['A']['token_usage']['shared_with'], ['A', 'B'])

    def test_central_requires_llm_policy(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            benchmark.run_episode('m', 'u', 'k', {}, 3, str(Path(folder) / 'x.jsonl'),
                                  policy_kind='tooluse', controller='central')


class RecoveryLimitTests(unittest.TestCase):
    def test_endless_code_failures_end_the_episode_instead_of_waiting_forever(self):
        from policy import CodePolicy
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()),                 patch.object(CodePolicy, '_generate_code', side_effect=ValueError('context too long')),                 patch('policy.time.sleep'):
            path = Path(folder) / 'stuck.jsonl'
            benchmark.run_episode('test', 'https://example.test/v1', 'key', {}, 5, str(path),
                                  environment_kind='sequence_rooms', sequence_seed=3)
            score = json.loads(path.with_suffix('.score.json').read_text(encoding='utf-8'))
        self.assertIn('repair attempts', score['stopped'])
        self.assertFalse(score['team']['cleared'])

    def test_scenario_map_can_turn_on_reward_feedback(self):
        from mapgen.spec import MapSpec
        sys.path.insert(0, benchmark.HERE)
        from scenarios import load
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            path = Path(folder) / 'reward.jsonl'
            benchmark.run_episode('m', 'u', 'k', {}, 2, str(path), MapSpec.from_dict(
                load('s09_shared_budget').build().to_dict()), policy_kind='noop')
            record = json.loads(path.read_text(encoding='utf-8').splitlines()[0])
        self.assertTrue(record['reward_visible'])
        self.assertIn('observation.reward holds', record['task']['A'])
        self.assertEqual((record['prompt_contract'], record['disclose_costs']), ('v2', False))
        self.assertNotIn('Costs:', record['task']['A'])


class LongContextPenaltyTests(unittest.TestCase):
    def usage(self, prompt):
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=10, total_tokens=prompt + 10))

    def test_each_long_request_costs_the_squared_excess(self):
        from policy import CodePolicy
        env, _, objectives = build_sequence_rooms(seed=3)
        policy = CodePolicy('test', 'task')
        for prompt in (400_000, 600_000, 800_000, 1_200_000):
            tracker(policy.client).record(self.usage(prompt))
        env.agents['A'].set_policy(policy)
        agent = score_episode(env, 80, objectives)['agents']['A']
        self.assertEqual(agent['context_penalty'], -(10 + 90 + 250))
        self.assertEqual(agent['long_context_requests'], 3)
        self.assertIn('긴 context 요청 3회', [item['reason'] for item in agent['items']])
        self.assertEqual(policy.token_usage['max_prompt_tokens'], 1_200_000)

    def test_context_status_shows_the_last_request_size_and_rule(self):
        from policy import CodePolicy
        from context_memory import ContextConfig, ContextMemory
        policy = CodePolicy('test', 'task')
        tracker(policy.client).record(self.usage(700_000))
        history = [{'role': 'system', 'content': 'x'}]
        policy._prepare_context(history, 100)
        status = json.loads(history[-1]['content'].split('\n', 1)[1])
        self.assertEqual(status['last_request_prompt_tokens'], 700_000)
        self.assertNotIn('context_penalty_rule', status)  # 비용 규칙은 기본으로 숨김
        policy._context_memory = ContextMemory(ContextConfig(show_costs=True))
        policy._prepare_context(history, 100)
        status = json.loads(history[-1]['content'].split('\n', 1)[1])
        self.assertEqual(status['last_request_context_penalty'], 40.0)
        self.assertIn('exceeds 500000 tokens', status['context_penalty_rule'])
        self.assertIn('Costs: output tokens beyond 50,000', benchmark.penalty_description(ScoreConfig()))


class KeepCodeOnMessageTests(unittest.TestCase):
    CODE = 'def decide(o): return {"type": "noop", "recheck_after": 50}'
    NEW_CODE = 'def decide(o): return {"type": "turn", "angle": 5, "recheck_after": 50}'

    def observation(self, step, inbox):
        return {'self': {'step': step, 'x': 0., 'y': 0., 'facing': 0.}, 'inbox': inbox, 'memory': {},
                'known_objects': {}, 'visible_objects': [], 'walls': []}

    def reply(self, name, arguments):
        call = SimpleNamespace(id='c1', function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))
        message = SimpleNamespace(content=None, tool_calls=[call])
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls', message=message)], usage=None)

    def run_message(self, response):
        from unittest.mock import Mock
        from policy import CodePolicy
        policy = CodePolicy('test', 'task')
        policy.client = Mock()
        policy.client.chat.completions.create.return_value = response
        with patch.object(policy, '_generate_code', return_value=self.CODE):
            policy.decide(self.observation(1, []))
        message = {'type': 'text', 'from': 'B', 'content': 'hi', 'step': 1}
        action = policy.decide(self.observation(2, [message]))
        tools = [t['function']['name'] for t in policy.client.chat.completions.create.call_args.kwargs['tools']]
        return policy, action, tools

    def test_model_may_keep_working_code_when_a_message_arrives(self):
        policy, action, tools = self.run_message(self.reply('keep_current_code', {'reason': 'code reads the inbox'}))
        self.assertIn('keep_current_code', tools)
        self.assertEqual(policy.generated_code, self.CODE)
        self.assertTrue(policy.last_replan['kept'])
        self.assertEqual(action['type'], 'noop')

    def test_model_may_still_rewrite_the_code(self):
        policy, action, _ = self.run_message(self.reply('submit_policy_code', {'code': self.NEW_CODE}))
        self.assertEqual(policy.generated_code, self.NEW_CODE)
        self.assertNotIn('kept', policy.last_replan)
        self.assertEqual(action['type'], 'turn')


class EnvironmentChangeReviewTests(unittest.TestCase):
    CODE = 'def decide(o): return {"type": "noop", "recheck_after": 50}'

    def observation(self, step, known=None, notices=(), result=None, x=0.0):
        return {'self': {'step': step, 'x': x, 'y': 0., 'facing': 0., 'inventory': []}, 'inbox': [], 'memory': {},
                'known_objects': known or {}, 'visible_objects': [], 'walls': [], 'notices': list(notices),
                'last_action_result': result}

    def test_only_real_changes_trigger_reviews_up_to_the_cap(self):
        from policy import CodePolicy
        policy = CodePolicy('test', 'task', env_change_cap=2)
        door = lambda locked, x=10: {'door': {'object_id': 'door', 'type': 'door', 'x': x, 'y': 5, 'locked': locked,
                                              'last_seen_step': 1}}
        prompts = []

        def generate(prompt, allow_keep=False):
            prompts.append((prompt, allow_keep))
            return None if allow_keep else self.CODE
        with patch.object(policy, '_generate_code', side_effect=generate):
            policy.decide(self.observation(1, door(True)))                   # first code
            policy.decide(self.observation(2, door(True, x=30), x=5.0))      # moved / coordinates only: no review
            self.assertEqual(len(prompts), 1)
            policy.decide(self.observation(3, door(False, x=30)))            # door opened
            self.assertIn("door: locked True->False", prompts[-1][0])
            self.assertTrue(prompts[-1][1])
            self.assertTrue(policy.last_replan['kept'])
            self.assertEqual(policy.last_replan['kind'], 'env_changed')
            result = {'step': 3, 'action_type': 'pick_up', 'status': 'no_effect', 'reason': 'nothing'}
            policy.decide(self.observation(4, door(False), result=result))   # no-effect action
            self.assertIn('was no_effect', prompts[-1][0])
            policy.decide(self.observation(5, door(True), notices=[{'type': 'sequence_reset'}]))
            self.assertEqual(len(prompts), 3)                                 # cap of 2 reached
        self.assertEqual(policy.env_reviews, 2)

    def test_off_by_default_and_announced_when_enabled(self):
        from policy import CodePolicy
        self.assertEqual(CodePolicy('test', 'task').env_change_cap, 0)
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            path = Path(folder) / 'env.jsonl'
            benchmark.run_episode('m', 'u', 'k', {}, 1, str(path), policy_kind='noop',
                                  environment_kind='sequence_rooms', env_change_cap=4)
            record = json.loads(path.read_text(encoding='utf-8').splitlines()[0])
        self.assertIn('at most 4 times per episode', record['task']['A'])


class SandboxAllowanceTests(unittest.TestCase):
    def test_common_builtins_and_safe_modules_work_and_are_documented(self):
        from policy import CODE_POLICY_SYSTEM_PROMPT
        from policy_sandbox import run_decide_code
        code = ('import collections\nfrom itertools import product\n'
                'def decide(o):\n    print("debug")\n    seen = set(map(abs, [-1, 1, 2]))\n'
                '    queue = collections.deque(product([1], [2]))\n'
                '    return {"type": "noop", "n": len(seen) + len(queue) + divmod(7, 2)[0]}')
        self.assertEqual(run_decide_code(code, {'self': {'step': 1}}), {'action': {'type': 'noop', 'n': 6}, 'error': None})
        self.assertIn('Available built-ins: abs', CODE_POLICY_SYSTEM_PROMPT)
        self.assertIn('set', CODE_POLICY_SYSTEM_PROMPT)
        self.assertIn('import only collections, functools, heapq, itertools, math', CODE_POLICY_SYSTEM_PROMPT)

    def test_escape_routes_stay_closed(self):
        from policy_sandbox import run_decide_code
        for code in ('import os\ndef decide(o): return {"type": "noop"}',
                     'from . import x\ndef decide(o): return {"type": "noop"}',
                     'def decide(o): return getattr(o, "x")',
                     'def decide(o): return type(o)'):
            with self.subTest(code=code):
                self.assertIsNotNone(run_decide_code(code, {'self': {'step': 1}})['error'])


class ExperimentTests(unittest.TestCase):
    def test_statistics(self):
        low, high = experiment.wilson_interval(8, 8)
        self.assertAlmostEqual(high, 1.0)
        self.assertAlmostEqual(low, 0.676, places=3)
        self.assertEqual(experiment.mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(experiment.mcnemar_exact(0, 6), 0.03125)
        self.assertEqual(experiment.parse_seeds('1-3,5,3'), [1, 2, 3, 5])

    def test_paired_comparison_matches_seed_and_repeat(self):
        rows = [{'run': f'm__{c}__s{s}__r1.jsonl', 'model': 'm', 'controller': c, 'seed': s,
                 'complete': True, 'cleared': c == 'central' or s == 1}
                for s in (1, 2, 3) for c in ('decentralized', 'central')]
        result = experiment.paired_comparison(rows, ['decentralized', 'central'])[0]
        self.assertEqual((result['pairs'], result['both_cleared'], result['only_b_cleared']), (3, 1, 2))

    def test_runner_resumes_and_summarizes_without_api(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()), \
                patch.object(experiment, 'EXPERIMENTS_DIR', Path(folder)):
            argv = ['experiment.py', '--name', 't', '--policy', 'tooluse', '--controllers', 'decentralized',
                    '--seeds', '1', '--steps', '5']
            with patch.object(sys, 'argv', argv):
                experiment.main()
            with patch.object(sys, 'argv', argv), patch.object(benchmark, 'run_episode') as run:
                experiment.main()
            run.assert_not_called()
            summary = json.loads((Path(folder) / 't' / 'summary.json').read_text(encoding='utf-8'))
            with patch.object(sys, 'argv', argv[:-2] + ['--steps', '6']), self.assertRaises(SystemExit):
                experiment.main()
        self.assertEqual(summary['by_condition'][0]['runs'], 1)
        self.assertEqual(summary['runs'][0]['controller'], 'decentralized')


class JudgeAgreementTests(unittest.TestCase):
    def test_metrics(self):
        same = {judge_agreement.turn_key(s, 'A'): v for s, v in enumerate([1, 4, 7, 9])}
        result = judge_agreement.compare(same, same)
        self.assertEqual((result['n'], result['pearson'], result['qwk'], result['mae']), (4, 1.0, 1.0, 0.0))
        flipped = {k: 10 - v for k, v in same.items()}
        self.assertEqual(judge_agreement.compare(same, flipped)['spearman'], -1.0)
        self.assertIsNone(judge_agreement.compare(same, {k: 5 for k in same})['pearson'])

    def test_judge_and_human_files_are_compared_on_common_turns(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'run.jsonl'
            manifest.write_text('', encoding='utf-8')
            for model, scores in (('j1', [8, 2, float('nan')]), ('j2', [7, 3, 5])):
                judge_agreement.save_judge_result(manifest, model, {
                    'raw_avg': 5.0, 'per_turn': [{'step': s, 'agent': 'A', 'score': v}
                                                 for s, v in enumerate(scores, 1)]})
            judge_agreement.save_human_score(manifest, '홍길동', 1, 'A', 9)
            judge_agreement.save_human_score(manifest, '홍길동', 2, 'A', 1)
            judge_agreement.save_human_score(manifest, '홍길동', 3, 'A', 4)
            judge_agreement.save_human_score(manifest, '홍길동', 3, 'A', None)
            with self.assertRaises(ValueError):
                judge_agreement.save_human_score(manifest, '홍길동', 1, 'A', 11)
            report = judge_agreement.report(manifest)
            stored = json.loads(judge_agreement.judge_path(manifest).read_text(encoding='utf-8'))
        self.assertIsNone(stored['j1']['per_turn'][2]['score'])
        pairs = {(p['a'], p['b']): p for p in report['pairs']}
        self.assertEqual(pairs[('판정:j1', '사람:홍길동')]['n'], 2)
        self.assertEqual(pairs[('판정:j1', '판정:j2')]['n'], 2)
        self.assertIn(('사람:홍길동', judge_agreement.JUDGE_MEAN), pairs)
        self.assertNotIn(('판정:j1', judge_agreement.JUDGE_MEAN), pairs)

    def test_baselines_are_kept_per_judge(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(maci_judge, 'BASELINE_FILE', str(Path(folder) / 'b.json')):
            maci_judge.save_baseline('base', 5.0, 'judge1')
            self.assertEqual(maci_judge.scale_score(10.0, 'base', 'judge1'), (200.0, 5.0))
            self.assertEqual(maci_judge.scale_score(10.0, 'base', 'judge2'), (None, None))


class HumanScoringTabTests(unittest.TestCase):
    def setUp(self):
        import launcher
        self.launcher = launcher
        self.app = launcher.Launcher()

    def tearDown(self):
        self.launcher.pygame.quit()

    def test_human_tab_scores_turns_and_reports_agreement(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'run.jsonl'
            lines = [{'step': s, 'task': {'A': 't'}, 'objectives': [], 'messages': [],
                      'agents': [{'agent': 'A', 'position': [0, 0], 'generated_code': 'def decide(o): pass',
                                  'decision': {'action': {'type': 'noop'}, 'final_action': {'type': 'noop'}}}]}
                     for s in (1, 2)]
            manifest.write_text('\n'.join(json.dumps(l) for l in lines), encoding='utf-8')
            self.app.fields['manifest'] = str(manifest)
            self.app.switch('사람 채점')
            self.app.draw()
            self.app.act(self.app.load_human_items)
            self.assertIn('채점자', self.app.status)
            self.app.fields['rater'] = 'tester'
            self.app.load_human_items()
            self.app.draw()
            self.assertTrue(any('def decide' in line for line in self.app.human_lines))
            self.app.set_human_score(7)
            self.assertEqual(self.app.human_index, 1)
            self.app.next_unscored()
            self.app.set_human_score(3)
            self.app.draw()
            judge_agreement.save_judge_result(manifest, 'j', {'raw_avg': 5, 'per_turn': [
                {'step': 1, 'agent': 'A', 'score': 8}, {'step': 2, 'agent': 'A', 'score': 2}]})
            self.app.human_agreement()
        self.assertTrue(any('공통 2턴' in line and 'r=1.000' in line for line in self.app.logs))

    def test_central_toggle_adds_controller_flag(self):
        self.app.policy = 'code'
        self.app.controller = 'central'
        self.app.fields['url'] = 'http://127.0.0.1:8080/v1'
        with patch.object(self.app, 'start') as start, patch.object(self.app, 'open_viewer'):
            self.app.run_episode()
        args = start.call_args.args[0]
        self.assertEqual(args[args.index('--controller') + 1], 'central')
        self.app.policy = 'tooluse'
        self.app.act(self.app.run_episode)
        self.assertIn('단일 LLM', self.app.status)
        self.app.switch('실행')
        self.app.draw()


if __name__ == '__main__':
    unittest.main()
