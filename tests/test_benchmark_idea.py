"""Replay information boundary, verdict validation and efficiency comparison."""
import json
from pathlib import Path
from types import SimpleNamespace as NS
from tempfile import TemporaryDirectory
import unittest

import benchmark_idea as idea


def record(step, *, messages=(), events=(), level=3, completed=(), solo_agent=None):
    return {'step': step, 'environment': 'curriculum', 'map_seed': 42,
            'objectives': [{'type': 'door_unlocked', 'door_id': 'vault'}],
            'reveal_goal': True, 'reward_visible': False, 'solo_agent': solo_agent,
            'configured_steps': 2,
            'task': {'A': 'shared goal'},
            'messages': list(messages), 'events': list(events), 'cleared': False,
            'world': {'level_state': {'level': level, 'total_levels': 5,
                                     'completed_levels': list(completed)}},
            'agents': [{'agent': 'A', 'model': 'test', 'decision': {'action': {'type': 'noop'},
                                                 'final_action': {'type': 'noop'}}}]}


class SnapshotTests(unittest.TestCase):
    def test_selects_event_and_routine_snapshots(self):
        records = [record(i) for i in range(1, 7)]
        records[1]['messages'] = [{'sender_id': 'B', 'receiver_id': 'A', 'content': 'wait'}]
        records[3]['events'] = [{'type': 'sequence_reset'}]
        records[5]['events'] = [{'type': 'level_completed'}]
        selected = idea.select_snapshots(records, 4)
        self.assertEqual({reason for _, reason in selected},
                         {'message', 'reset', 'level_completed', 'routine_control'})
        self.assertEqual(selected, idea.select_snapshots(records, 4))

    def test_loads_only_original_own_observation_for_snapshot(self):
        with TemporaryDirectory() as folder:
            manifest = Path(folder) / 'run.jsonl'
            archive = manifest.with_suffix('.context_archive.jsonl')
            observation = {'self': {'step': 7}, 'memory': {'private': 'A-only'}}
            message = {'role': 'user', 'content': 'Simulation step result:\n' + json.dumps(
                {'observation': observation, 'next_observation': {'self': {'step': 8}}})}
            archive.write_text(json.dumps({'agent': 'A', 'message': message}) + '\n', encoding='utf-8')
            loaded = idea.load_observations(manifest)
        self.assertEqual(loaded[('A', 7)], observation)
        self.assertNotIn(('B', 7), loaded)

    def test_replay_does_not_receive_observer_state_or_future_events(self):
        snapshot = idea.build_snapshot([record(1), record(2, level=4)], 1, 'A',
                                       {('A', 2): {'self': {'step': 2}, 'memory': {'clue': 'maybe 3'}}})
        self.assertEqual(snapshot['observer_state_before']['level_state']['level'], 3)
        captured = {}
        class Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        captured.update(json.loads(kwargs['messages'][1]['content']))
                        return NS(choices=[NS(finish_reason='stop', message=NS(content=json.dumps({
                            'situation_report': 'Partner progress unknown', 'action': {'type': 'noop'}})))])
        proposal = idea.replay_snapshot(Client(), 'agent-model', snapshot)
        self.assertEqual(proposal['action']['type'], 'noop')
        self.assertNotIn('observer_state_before', captured)
        self.assertNotIn('observer_state_after', captured)
        self.assertNotIn('current_events', captured)

    def test_replay_repairs_one_malformed_response(self):
        snapshot = idea.build_snapshot([record(1)], 0, 'A',
                                       {('A', 1): {'self': {'step': 1}}})
        calls = []
        class Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        calls.append(kwargs)
                        content = '{broken' if len(calls) == 1 else json.dumps({
                            'situation_report': 'Partner state unknown', 'action': {'type': 'noop'}})
                        return NS(choices=[NS(finish_reason='stop', message=NS(content=content))])
        self.assertEqual(idea.replay_snapshot(Client(), 'actor', snapshot)['action']['type'], 'noop')
        self.assertEqual(len(calls), 2)

    def test_verdict_needs_real_evidence_and_action_is_validated(self):
        packet = {**idea.build_snapshot([record(1)], 0, 'A', {}),
                  'proposal': {'situation_report': 'unknown', 'action': {'type': 'noop'}}}
        verdict = {'situation': {'score': 2, 'reason': 'limited view',
                                 'evidence': ['proposal.situation_report']},
                   'action_fit': {'score': 2, 'reason': 'plausible pause',
                                  'evidence': ['proposal.action']}}
        self.assertEqual(idea.parse_verdict(json.dumps(verdict), packet), verdict)
        verdict['situation']['evidence'] = ['missing']
        with self.assertRaises(ValueError):
            idea.parse_verdict(json.dumps(verdict), packet)
        with self.assertRaises(ValueError):
            idea.validate_action({'type': 'move_forward', 'distance': -1})

    def test_judge_sees_fact_check_after_replay_and_scores_both_dimensions(self):
        snapshot = idea.build_snapshot([record(1), record(2)], 1, 'A',
                                       {('A', 2): {'self': {'step': 2}, 'memory': {'plan': 'wait'}}})
        proposal = {'situation_report': 'Partner state unknown', 'action': {'type': 'noop'}}
        captured = {}
        verdict = {'situation': {'score': 4, 'reason': 'calibrated uncertainty',
                                 'evidence': ['proposal.situation_report', 'agent_observation.memory']},
                   'action_fit': {'score': 3, 'reason': 'consistent with waiting plan',
                                  'evidence': ['proposal.action', 'agent_observation.memory']}}
        class Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        captured.update(json.loads(kwargs['messages'][1]['content']))
                        return NS(choices=[NS(finish_reason='stop', message=NS(content=json.dumps(verdict)))])
        self.assertEqual(idea.judge_snapshot(Client(), 'judge-model', snapshot, proposal), verdict)
        self.assertIn('observer_state_before', captured)
        self.assertEqual(captured['proposal'], proposal)

    def test_named_known_target_move_away_is_detected_without_hidden_map(self):
        snapshot = {'agent_observation': {'self': {'x': 100, 'y': 100, 'facing': 180,
                                                   'max_move': 20},
                                          'known_objects': {'pad_A9': {'object_id': 'pad_A9',
                                                                       'x': 130, 'y': 100}},
                                          'visible_objects': []}}
        proposal = {'situation_report': 'My next target is pad_A9.',
                    'action': {'type': 'move_forward', 'distance': 20}}
        geometry = idea.action_geometry(snapshot, proposal)
        self.assertEqual(geometry['distance_change_if_unblocked'], 20)
        self.assertEqual(geometry['named_known_target'], 'pad_A9')

    def test_geometry_keeps_each_named_target_and_turn_direction(self):
        snapshot = {'agent_observation': {'self': {'x': 100, 'y': 100, 'facing': 0,
                                                   'max_move': 20},
                                          'known_objects': {
                                              'pad_A0': {'object_id': 'pad_A0', 'x': 80, 'y': 100},
                                              'pad_A9': {'object_id': 'pad_A9', 'x': 120, 'y': 100}},
                                          'visible_objects': []}}
        proposal = {'situation_report': 'I left pad_A0 and now approach pad_A9.',
                    'action': {'type': 'move_forward', 'distance': 10}}
        targets = idea.action_geometry(snapshot, proposal)['named_targets']
        self.assertEqual(targets['pad_A0']['distance_change_if_unblocked'], 10)
        self.assertEqual(targets['pad_A9']['distance_change_if_unblocked'], -10)
        snapshot['agent_observation']['self']['facing'] = 270
        proposal['action'] = {'type': 'turn', 'angle': 90}
        turn_geometry = idea.action_geometry(snapshot, proposal)
        self.assertEqual(turn_geometry['facing_after_cardinal'], 'right')
        verdict = {'action_fit': {'reason': 'This points the agent down toward the target.'}}
        with self.assertRaises(ValueError):
            idea.validate_geometry_reason(verdict, turn_geometry)

    def test_judge_retries_when_distance_explanation_contradicts_geometry(self):
        snapshot = idea.build_snapshot([record(1)], 0, 'A', {('A', 1): {
            'self': {'step': 1, 'x': 100, 'y': 100, 'facing': 0, 'max_move': 20},
            'visible_objects': [{'object_id': 'pad_A9', 'x': 120, 'y': 100}]}})
        proposal = {'situation_report': 'I am approaching pad_A9.',
                    'action': {'type': 'move_forward', 'distance': 10}}
        verdict = {'situation': {'score': 3, 'reason': 'Observed accurately.',
                                 'evidence': ['proposal.situation_report']},
                   'action_fit': {'score': 2, 'reason': 'Moving increases distance to pad_A9.',
                                  'evidence': ['proposal.action']}}
        calls = []
        class Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        calls.append(kwargs)
                        if len(calls) == 2:
                            verdict['action_fit']['reason'] = 'Moving approaches pad_A9.'
                        return NS(choices=[NS(finish_reason='stop', message=NS(content=json.dumps(verdict)))])
        result = idea.judge_snapshot(Client(), 'judge', snapshot, proposal)
        self.assertEqual(len(calls), 2)
        self.assertIn('approaches', result['action_fit']['reason'])

    def test_judge_repairs_one_malformed_json_verdict(self):
        snapshot = idea.build_snapshot([record(1)], 0, 'A', {})
        proposal = {'situation_report': 'unknown', 'action': {'type': 'noop'}}
        verdict = {'situation': {'score': 2, 'reason': 'uncertain',
                                 'evidence': ['proposal.situation_report']},
                   'action_fit': {'score': 2, 'reason': 'pause', 'evidence': ['proposal.action']}}
        calls = []
        class Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        calls.append(kwargs)
                        text = '{broken' if len(calls) == 1 else json.dumps(verdict)
                        return NS(choices=[NS(finish_reason='stop', message=NS(content=text))])
        self.assertEqual(idea.judge_snapshot(Client(), 'judge', snapshot, proposal), verdict)
        self.assertEqual(len(calls), 2)

    def test_judge_retries_once_when_output_is_truncated(self):
        snapshot = idea.build_snapshot([record(1)], 0, 'A', {})
        proposal = {'situation_report': 'unknown', 'action': {'type': 'noop'}}
        verdict = {'situation': {'score': None, 'reason': 'uncertain', 'evidence': []},
                   'action_fit': {'score': 2, 'reason': 'pause', 'evidence': ['proposal.action']}}
        budgets = []
        class Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        budgets.append(kwargs['max_tokens'])
                        finish = 'length' if len(budgets) == 1 else 'stop'
                        return NS(choices=[NS(finish_reason=finish, message=NS(content=json.dumps(verdict)))])
        self.assertEqual(idea.judge_snapshot(Client(), 'judge', snapshot, proposal), verdict)
        self.assertEqual(budgets, [2000, 4000])

    def test_solo_efficiency_comparison_is_outcome_based(self):
        joint = [record(1), record(2, completed=(1, 2, 3))]
        solo = [record(1, solo_agent='A'), record(2, completed=(1, 2), solo_agent='A')]
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'solo.jsonl'
            path.write_text('\n'.join(json.dumps(r) for r in solo), encoding='utf-8')
            result = idea.compare_solo(Path(folder) / 'joint.jsonl', joint, [path])
        self.assertAlmostEqual(result['cooperation_index_delta'], 0.1)
        self.assertEqual(result['best_solo_efficiency'], 0.2)

    def test_efficiency_rewards_earlier_level_completion_at_same_final_progress(self):
        early = [record(i, completed=(1,) if i < 3 else (1, 2)) for i in range(1, 5)]
        late = [record(i, completed=(1,) if i < 4 else (1, 2)) for i in range(1, 5)]
        for run in (early, late):
            for row in run:
                row['configured_steps'] = 4
        self.assertEqual(idea.episode_efficiency(early)['progress'],
                         idea.episode_efficiency(late)['progress'])
        self.assertAlmostEqual(idea.episode_efficiency(early)['progress_auc'], 0.3)
        self.assertAlmostEqual(idea.episode_efficiency(late)['progress_auc'], 0.25)
        self.assertEqual(idea.episode_efficiency(early)['completion_steps'], [1, 3])


if __name__ == '__main__':
    unittest.main()
