"""Agent reasoning capture (policy.py -> <run>.agent_reasoning.jsonl) and the decision-point judge review."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'enviroment'))

import judge_agreement  # noqa: E402
import judge_context  # noqa: E402
import llm_outputs  # noqa: E402
from context_memory import ContextHistory  # noqa: E402
from policy import _generate_code_with_submission_gate, response_reasoning  # noqa: E402
from tests.test_judge_context import write_run  # noqa: E402

CODE = 'def decide(o): return {"type": "noop"}'


def message(content=None, extra=None, calls=()):
    m = SimpleNamespace(content=content, tool_calls=list(calls) or None)
    m.model_extra = extra or {}
    return m


class ResponseReasoningTests(unittest.TestCase):
    def test_reads_the_reasoning_field(self):
        found = response_reasoning(message(extra={'reasoning': 'A is 3 moves away, so wait 2 steps'}))
        self.assertEqual(found, {'reasoning': 'A is 3 moves away, so wait 2 steps', 'hidden': False})

    def test_falls_back_to_reasoning_details_and_think_tags(self):
        found = response_reasoning(message(extra={'reasoning_details': [{'type': 'reasoning.summary',
                                                                          'summary': 'plan: sync at 5'}]}))
        self.assertEqual(found['reasoning'], 'plan: sync at 5')
        self.assertEqual(response_reasoning(message(content='<think>count steps</think>ok'))['reasoning'],
                         'count steps')

    def test_encrypted_reasoning_is_marked_hidden(self):
        found = response_reasoning(message(extra={'reasoning_details': [{'type': 'reasoning.encrypted',
                                                                          'data': 'xyz'}]}))
        self.assertEqual(found, {'reasoning': '', 'hidden': True})


class ReasoningCaptureTests(unittest.TestCase):
    def test_reasoning_goes_to_its_own_sink_and_never_into_the_conversation(self):
        call = SimpleNamespace(id='call-1', function=SimpleNamespace(name='submit_policy_code',
                                                                     arguments=json.dumps({'code': CODE})))
        usage = SimpleNamespace(completion_tokens_details=SimpleNamespace(reasoning_tokens=12))
        response = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason='tool_calls', message=message(extra={'reasoning': 'B is slower; enter at step 5'},
                                                        calls=[call]))], usage=usage)
        client = Mock()
        client.chat.completions.create.return_value = response
        history, records = ContextHistory(), []
        history.reasoning_sink = records.append
        code = _generate_code_with_submission_gate(client, 'm', 'sys', 'task', 0.0, 100, {}, history=history)
        self.assertEqual(code, CODE)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['tool_call_ids'], ['call-1'])
        self.assertEqual(records[0]['reasoning'], 'B is slower; enter at step 5')
        self.assertEqual(records[0]['reasoning_tokens'], 12)
        self.assertNotIn('enter at step 5', json.dumps(list(history)))


class AgentReasoningOptionTests(unittest.TestCase):
    def run_gate(self, extra_params, replies):
        client = Mock()
        client.chat.completions.create.side_effect = replies
        code = _generate_code_with_submission_gate(client, 'm', 'sys', 'task', 0.0, 100, extra_params,
                                                   history=ContextHistory())
        return code, client.chat.completions.create.call_args_list

    def reply(self, calls=(), content=None):
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls' if calls else 'stop',
                                                        message=message(content=content, calls=calls))], usage=None)

    def submit(self):
        return SimpleNamespace(id='c1', function=SimpleNamespace(name='submit_policy_code',
                                                                 arguments=json.dumps({'code': CODE})))

    def test_default_forces_tool_calls(self):
        _, calls = self.run_gate({}, [self.reply([self.submit()])])
        self.assertEqual(calls[0].kwargs['tool_choice'], 'required')
        self.assertNotIn('extra_body', calls[0].kwargs)

    def test_agent_reasoning_asks_for_reasoning_and_lets_the_model_choose(self):
        from policy import agent_reasoning_params
        # 글로만 답해도 하네스가 도구를 쓰라고 다시 묻고, 그다음 제출을 받음
        code, calls = self.run_gate(agent_reasoning_params('low'),
                                    [self.reply(content='let me think'), self.reply([self.submit()])])
        self.assertEqual(code, CODE)
        self.assertEqual(calls[0].kwargs['tool_choice'], 'auto')
        self.assertEqual(calls[0].kwargs['extra_body'], {'reasoning': {'effort': 'low'}})
        self.assertEqual(len(calls), 2)


class ReasoningSummaryTests(unittest.TestCase):
    SUMMARY = 'B said pad_B is ready, so I enter pad_A at step 9 to sync.'

    def run_gate(self, extra_params):
        call = SimpleNamespace(id='call-9', function=SimpleNamespace(name='submit_policy_code', arguments=json.dumps(
            {'code': CODE, 'reasoning_summary': self.SUMMARY})))
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=200, total_tokens=300)
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason='tool_calls', message=message(calls=[call]))], usage=usage)
        history, records = ContextHistory(), []
        history.reasoning_sink = records.append
        code = _generate_code_with_submission_gate(client, 'm', 'sys', 'task', 0.0, 100, extra_params,
                                                   history=history)
        return code, client, history, records

    def test_summary_is_asked_for_saved_apart_and_kept_out_of_the_conversation(self):
        from policy import REASONING_SUMMARY_FIELD
        code, client, history, records = self.run_gate({REASONING_SUMMARY_FIELD: True})
        self.assertEqual(code, CODE)
        kwargs = client.chat.completions.create.call_args.kwargs
        submit = next(t for t in kwargs['tools'] if t['function']['name'] == 'submit_policy_code')
        self.assertIn('reasoning_summary', submit['function']['parameters']['required'])
        self.assertNotIn(REASONING_SUMMARY_FIELD, kwargs)  # harness option, never sent to the API
        self.assertIn('Reasoning summary:', history[0]['content'])
        self.assertEqual(records[0]['summary'], self.SUMMARY)
        self.assertGreater(records[0]['summary_tokens_estimate'], 0)
        self.assertNotIn('pad_A at step 9', json.dumps(list(history)))

    def test_summary_tokens_are_not_charged_as_output_tokens(self):
        from policy import REASONING_SUMMARY_FIELD, summary_token_estimate
        from token_usage import tracker
        _, client, _, _ = self.run_gate({REASONING_SUMMARY_FIELD: True})
        counts = tracker(client).snapshot()
        self.assertEqual(counts['reasoning_summary_tokens'], summary_token_estimate(self.SUMMARY))
        from scoring import ScoreConfig, score_episode
        env = SimpleNamespace(event_log=SimpleNamespace(entries=[], filter=lambda **k: []),
                              decision_log=SimpleNamespace(entries=[]), step_count=1,
                              agents={'A': SimpleNamespace(policy=SimpleNamespace(
                                  token_usage=dict(counts, completion_tokens=60_000 + counts['reasoning_summary_tokens']),
                                  prompt_history=[], code_checks=None))})
        score = score_episode(env, 10, [{'type': 'never'}], ScoreConfig())
        self.assertEqual(score['agents']['A']['token_penalty'], -1.0)  # only the 10,000 tokens above 50,000 count

    def test_without_the_option_nothing_changes(self):
        _, client, history, records = self.run_gate({})
        kwargs = client.chat.completions.create.call_args.kwargs
        submit = next(t for t in kwargs['tools'] if t['function']['name'] == 'submit_policy_code')
        self.assertNotIn('reasoning_summary', submit['function']['parameters']['properties'])
        self.assertNotIn('Reasoning summary:', history[0]['content'])


class ReasoningInReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manifest = write_run(Path(self.tmp.name))
        llm_outputs.reasoning_path(self.manifest).write_text(json.dumps(
            {'agent': 'A', 'step': 9, 'tool_call_ids': ['A3'], 'reasoning': 'B is ready, so I wait for GO',
             'hidden': False}) + '\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_outputs_and_judge_bundles_carry_the_agent_reasoning(self):
        output = next(o for o in llm_outputs.extract_outputs(self.manifest) if o['id'] == 'A:3')
        self.assertEqual(output['reasoning'], 'B is ready, so I wait for GO')
        bundle = judge_context.build_bundles(self.manifest, agent_filter='A', min_anchors=0)[1]
        self.assertIn('agent reasoning: B is ready, so I wait for GO', judge_context.render(bundle))

    def test_anchor_ratings_and_judges_stay_apart_from_step_scores(self):
        bundle = judge_context.build_bundles(self.manifest, agent_filter='A', min_anchors=0)[1]
        judge_context.save_anchor_rating(self.manifest, 'kim', bundle, 6, 'used the message')
        self.assertEqual(judge_context.load_anchor_ratings(self.manifest, 'kim')['9|A']['score'], 6)
        judge_agreement.save_judge_result(self.manifest, 'judge-x' + judge_agreement.ANCHOR_SUFFIX,
                                          {'raw_avg': 8.0, 'per_turn': [{'step': 9, 'agent': 'A', 'score': 8.0}]})
        judge_agreement.save_judge_result(self.manifest, 'judge-x',
                                          {'raw_avg': 2.0, 'per_turn': [{'step': 9, 'agent': 'A', 'score': 2.0}]})
        self.assertEqual(judge_context.judge_scores(self.manifest), {'judge-x': {'9|A': 8.0}})
        self.assertEqual(list(judge_agreement.load_judges(self.manifest)), ['judge-x'])
        self.assertIn('판단 시점', judge_context.summary(self.manifest, [bundle], 'kim'))

    def test_log_app_judge_screen_scores_and_rates_decision_points(self):
        import pi_logs
        app = pi_logs.PiLogsApp('unused', 'unused', local_dir=str(self.manifest.parent), source='local')
        try:
            app.judge_client = lambda: None  # no network: lexical retrieval
            app.selected = self.manifest.name
            app.fields['rater'] = 'kim'
            app.open_judge()
            deadline = time.time() + 30
            while app.judge is None and time.time() < deadline:
                app.poll()
                time.sleep(0.05)
            self.assertTrue(app.judge['bundles'])
            app.draw()
            app.rate_point(7)
            self.assertEqual(len(judge_context.load_anchor_ratings(self.manifest, 'kim')), 1)
            app.judge_client = lambda: object()
            with patch('maci_judge.ask_judge', return_value=5.0):
                app.run_judge()
                while app.busy and time.time() < deadline:
                    app.poll()
                    time.sleep(0.05)
            self.assertIn('완료', app.status)
            self.assertTrue(all(v == 5.0 for s in judge_context.judge_scores(self.manifest).values()
                                for v in s.values()))
            app.draw()
        finally:
            app.pygame.quit()


if __name__ == '__main__':
    unittest.main()


class ToolChoiceFallbackTests(unittest.TestCase):
    def test_models_that_reject_forced_tool_choice_fall_back_to_auto(self):
        from policy import _generate_code_with_submission_gate as gate
        submit = SimpleNamespace(id='c1', function=SimpleNamespace(name='submit_policy_code',
                                                                   arguments=json.dumps({'code': CODE})))
        ok = SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls', message=message(calls=[submit]))],
                             usage=None)
        client = Mock()
        client.chat.completions.create.side_effect = [
            ValueError('tool_choice: type "tool" and "any" are not supported for this model.'), ok, ok]
        self.assertEqual(gate(client, 'm', 'sys', 'task', 0.0, 100, {}, history=ContextHistory()), CODE)
        choices = [c.kwargs['tool_choice'] for c in client.chat.completions.create.call_args_list]
        self.assertEqual(choices, ['required', 'auto'])
        gate(client, 'm', 'sys', 'task', 0.0, 100, {}, history=ContextHistory())
        self.assertEqual(client.chat.completions.create.call_args.kwargs['tool_choice'], 'auto')  # remembered
