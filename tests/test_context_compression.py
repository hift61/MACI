"""Only the acting model chooses and writes context compaction."""
import copy
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch

import benchmark
from context_memory import ContextHistory, ContextMemory, ContextConfig, SUMMARY_PREFIX, STATUS_PREFIX
from policy import CodePolicy
from token_usage import tracker


def source_history():
    history = ContextHistory([{'role': 'system', 'content': 'Agent A rules'}])
    for step in range(20):
        history.append({'role': 'user', 'content': 'Simulation step result:\n' + str(step) + 'x' * 1000})
    history.append({'role': 'user', 'content': 'Current observation:\nCURRENT_STATE_NEW_MESSAGE_AND_CODE'})
    return history


class ContextCompressionTests(unittest.TestCase):
    def test_pressure_is_advisory_and_never_summarizes_or_removes_history(self):
        history = source_history()
        originals = copy.deepcopy(list(history))
        memory = ContextMemory(ContextConfig(max_tokens=1))
        memory.prepare(history, 4000)
        self.assertEqual(history[:-1], originals)
        status = json.loads(history[-1]['content'][len(STATUS_PREFIX):])
        self.assertTrue(status['pressure'])
        self.assertFalse(status['automatic_compaction'])
        self.assertEqual(memory.events, [])

    def test_model_summary_used_verbatim_and_originals_preserved(self):
        history = source_history()
        originals = copy.deepcopy(history.archive)
        summary = 'Model-selected memory: verified input 2 at position 4; B claims wait.\nKeep this wording.'
        memory = ContextMemory()
        memory.compact(history, summary, 2)
        self.assertEqual(history.archive, originals)
        self.assertEqual(history[0], originals[0])
        self.assertEqual(history[-3:], originals[-3:])
        self.assertEqual(history[1]['content'], SUMMARY_PREFIX + summary)
        self.assertEqual(memory.events[-1]['mode'], 'model_directed')

    def test_tool_transactions_and_current_observation_protected(self):
        history = source_history()
        history.append({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'pending', 'type': 'function', 'function': {'name': 'manage_context', 'arguments': '{}'}}]})
        history.append({'role': 'tool', 'tool_call_id': 'pending', 'content': 'result'})
        protected = copy.deepcopy(history[-3:])
        ContextMemory().compact(history, 'model summary', 0)
        self.assertEqual(history[-3:], protected)

    def test_request_copy_does_not_duplicate_archive_or_sink(self):
        history = source_history()
        streamed = []
        history.sink = streamed.append
        request = copy.deepcopy(history)
        self.assertIs(type(request), list)
        self.assertEqual(streamed, [])
        history.extend([{'role': 'assistant', 'content': 'reply'}])
        self.assertEqual(streamed, [history[-1]])
        self.assertEqual(history.archive[-1], history[-1])

    def test_invalid_or_nonshrinking_proposals_leave_history_intact(self):
        history = source_history()
        old = copy.deepcopy(history)
        for args in [('', 0), ('summary', -1), ('summary', True), ('x' * 50_000, 0), ('summary', 999)]:
            with self.assertRaises(ValueError):
                ContextMemory().compact(history, *args)
            self.assertEqual(history, old)

    def test_inbox_is_full_unless_model_selects_retention_and_new_messages_survive(self):
        policy = CodePolicy('test', 'task')
        policy._reviewed_inbox_count = 20
        observation = {'inbox': [{'step': n, 'content': str(n)} for n in range(25)]}
        self.assertEqual(policy._prompt_observation(observation), observation)

    def test_model_selected_inbox_retention(self):
        policy = CodePolicy('test', 'task')
        policy.conversation_history.extend(source_history())
        policy._reviewed_inbox_count = 20
        observation = {'inbox': [{'step': n, 'content': str(n)} for n in range(25)]}
        policy._manage_context(summary='model memory', keep_recent_messages=0, inbox_recent_messages=2)
        prompt = policy._prompt_observation(observation)
        self.assertEqual(prompt['inbox'], observation['inbox'][18:])
        self.assertEqual(len(observation['inbox']), 25)
        policy.remember_step(observation, {'type': 'noop'}, observation)
        feedback = json.loads(policy.conversation_history[-1]['content'].split('\n', 1)[1])
        raw = json.loads(policy.conversation_history.archive[-1]['content'].split('\n', 1)[1])
        self.assertEqual(len(feedback['next_observation']['inbox']), 7)
        self.assertEqual(len(raw['next_observation']['inbox']), 25)

    def test_model_can_compact_then_submit_code_in_next_tool_round(self):
        policy = CodePolicy('test', 'task')
        policy.conversation_history.extend(source_history()[:-1])
        code = 'def decide(obs): return {"type":"noop"}'
        requests = []
        def create(client, **kwargs):
            requests.append(kwargs['messages'])
            name, args = ('manage_context', {'summary': 'Model memory', 'keep_recent_messages': 0}) if len(requests) == 1 else (
                'submit_policy_code', {'code': code})
            call = NS(id='call-' + str(len(requests)), function=NS(name=name, arguments=json.dumps(args)))
            return NS(choices=[NS(finish_reason='stop', message=NS(content=None, tool_calls=[call]))])
        with patch('policy._create_with_retry', side_effect=create):
            self.assertEqual(policy._generate_code('Current observation:\nNewest input'), code)
        self.assertEqual(len(requests), 2)
        self.assertTrue(any(m['role'] == 'tool' and json.loads(m['content']).get('applied') for m in requests[1]))
        self.assertTrue(any('Newest input' in (m.get('content') or '') for m in requests[1]))
        self.assertEqual(len(policy.context_memory.events), 1)

    def test_benchmark_model_tool_and_code_execute_with_original_audit(self):
        policies = [CodePolicy('test', 'task A'), CodePolicy('test', 'task B')]
        code = 'def decide(obs): return {"type":"noop","recheck_after":1}'
        calls = {}
        def create(client, **kwargs):
            count = calls.get(id(client), 0) + 1
            calls[id(client)] = count
            self.assertIn('manage_context', [t['function']['name'] for t in kwargs['tools']])
            tool_calls = []
            if count == 3:
                tool_calls.append(NS(id='memory', function=NS(name='manage_context', arguments=json.dumps(
                    {'summary': 'Model wrote: no number-pad input yet.', 'keep_recent_messages': 0}))))
            tool_calls.append(NS(id='submit', function=NS(name='submit_policy_code', arguments=json.dumps({'code': code}))))
            response = NS(choices=[NS(finish_reason='stop', message=NS(content=None, tool_calls=tool_calls))],
                          usage=NS(prompt_tokens=100, completion_tokens=20, total_tokens=120))
            tracker(client).record(response)
            return response
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run.jsonl'
            with patch.object(benchmark, 'make_policy', side_effect=policies), patch(
                    'policy._create_with_retry', side_effect=create), contextlib.redirect_stdout(io.StringIO()):
                benchmark.run_episode('test', '', '', {}, 8, str(path), context_max_tokens=1)
            audit = [json.loads(l) for l in path.with_suffix('.context_compressions.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(audit), 2)
            self.assertTrue(all(e['mode'] == 'model_directed' for e in audit))
            raw = json.loads(path.with_suffix('.context.json').read_text(encoding='utf-8'))
            working = json.loads(path.with_suffix('.working_context.json').read_text(encoding='utf-8'))
            streamed = [json.loads(l) for l in path.with_suffix('.context_archive.jsonl').read_text(encoding='utf-8').splitlines()]
            for aid, policy in zip(('A', 'B'), policies):
                self.assertEqual(raw[aid], [r['message'] for r in streamed if r['agent'] == aid])
                self.assertGreater(len(raw[aid]), len(working[aid]))
                self.assertTrue(any((m.get('content') or '').startswith(SUMMARY_PREFIX) for m in working[aid]))
                self.assertEqual(policy.token_usage['requests'], 8)
                self.assertEqual(policy.generated_code, code)
