"""Per-output human rating: extraction from the conversation archive, storage, and the log-app screen."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import json
from pathlib import Path
import tempfile
import time
import unittest

import llm_outputs
import pi_logs


def call(call_id, name, arguments):
    return {'id': call_id, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}


def archive(path):
    step = lambda n: 'Simulation step result:\n' + json.dumps({'observation': {'self': {'step': n}}})
    rows = [
        ('A', {'role': 'system', 'content': 'rules'}),
        ('A', {'role': 'user', 'content': 'task for A'}),
        ('A', {'role': 'user', 'content': 'Context management status (advisory):\n{}'}),
        ('A', {'role': 'assistant', 'content': None, 'tool_calls': [call('c1', 'submit_policy_code', {'code': 'def decide(o): pass'})]}),
        ('A', {'role': 'tool', 'tool_call_id': 'c1', 'content': '{"accepted": false, "error": "bad"}'}),
        ('B', {'role': 'assistant', 'content': 'thinking', 'tool_calls': [call('c2', 'keep_current_code', {'reason': 'fine'})]}),
        ('A', {'role': 'user', 'content': step(4)}),
        ('A', {'role': 'user', 'content': 'New incoming messages ...'}),
        ('A', {'role': 'assistant', 'content': None, 'tool_calls': [call('c3', 'manage_context', {'summary': 's', 'keep_recent_messages': 2}),
                                                                    call('c4', 'submit_policy_code', {'code': 'v2'})]}),
        ('A', {'role': 'tool', 'tool_call_id': 'c3', 'content': '{"applied": true}'}),
        ('A', {'role': 'tool', 'tool_call_id': 'c4', 'content': '{"accepted": true}'}),
    ]
    path.write_text('\n'.join(json.dumps({'agent': a, 'message': m}) for a, m in rows), encoding='utf-8')


class LlmOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manifest = Path(self.temp.name) / 'run.jsonl'
        self.manifest.write_text('', encoding='utf-8')
        archive(llm_outputs.archive_path(self.manifest))

    def tearDown(self):
        self.temp.cleanup()

    def test_each_assistant_message_is_one_output_with_its_input_and_result(self):
        outputs = llm_outputs.extract_outputs(self.manifest)
        self.assertEqual([o['id'] for o in outputs], ['A:1', 'B:1', 'A:2'])
        first, keep, second = outputs
        self.assertEqual(first['input'], 'task for A')  # the advisory status is skipped
        self.assertIn('def decide(o): pass', first['output'])
        self.assertEqual(first['result'], ['{"accepted": false, "error": "bad"}'])
        self.assertEqual(keep['tools'], ['keep_current_code'])
        self.assertIn('thinking', keep['output'])
        self.assertEqual((second['step'], second['input']), (5, 'New incoming messages ...'))
        self.assertEqual(len(second['result']), 2)

    def test_ratings_are_saved_per_rater_and_summarized(self):
        outputs = llm_outputs.extract_outputs(self.manifest)
        llm_outputs.save_rating(self.manifest, '평가자 1', outputs[0], 3, ' rejected code ')
        llm_outputs.save_rating(self.manifest, '평가자 1', outputs[2], 9)
        llm_outputs.save_rating(self.manifest, '평가자 1', outputs[2], None)
        llm_outputs.save_rating(self.manifest, '평가자 1', outputs[1], 7)
        with self.assertRaises(ValueError):
            llm_outputs.save_rating(self.manifest, '평가자 1', outputs[0], 11)
        ratings = llm_outputs.load_ratings(self.manifest, '평가자 1')
        self.assertEqual({k: v['score'] for k, v in ratings.items()}, {'A:1': 3, 'B:1': 7})
        self.assertEqual(ratings['A:1']['comment'], 'rejected code')
        self.assertEqual(llm_outputs.load_ratings(self.manifest, 'other'), {})
        self.assertIn('평가 2/3', llm_outputs.summary(outputs, ratings))

    def test_missing_archive_explains_how_to_get_it(self):
        with self.assertRaisesRegex(FileNotFoundError, '대화 이력 포함'):
            llm_outputs.extract_outputs(Path(self.temp.name) / 'none.jsonl')


class ReviewScreenTests(unittest.TestCase):
    def test_local_run_outputs_can_be_rated_from_the_log_app(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'run.jsonl'
            manifest.write_text(json.dumps({'step': 1, 'agents': [{'agent': 'A', 'model': 'm'}]}) + '\n', encoding='utf-8')
            archive(llm_outputs.archive_path(manifest))
            app = pi_logs.PiLogsApp('', '', local_dir=folder, source='local')
            try:
                app.selected = 'run.jsonl'
                app.open_review()
                self.assertIn('평가자', app.status)
                app.fields['rater'] = 'tester'
                app.open_review()
                deadline = time.time() + 30
                while app.review is None and time.time() < deadline:
                    app.poll()
                    time.sleep(0.05)
                app.draw()
                self.assertEqual(app.current_output()['id'], 'A:1')
                app.fields['comment'] = 'rejected'
                app.rate(4)
                self.assertEqual(app.current_output()['id'], 'B:1')  # jumps to the next unrated output
                app.set_filter('A')
                app.move_review(1)
                app.rate(8)
                app.draw()
                saved = llm_outputs.load_ratings(manifest, 'tester')
                self.assertEqual({k: v['score'] for k, v in saved.items()}, {'A:1': 4, 'A:2': 8})
                self.assertEqual(saved['A:1']['comment'], 'rejected')
            finally:
                app.pygame.quit()


if __name__ == '__main__':
    unittest.main()
