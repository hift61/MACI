"""Five interactive levels with feedback and persistent agent learning."""
import copy
import random

from blind_code import BlindCodeEnvironment
from sequence_rooms import build_sequence_rooms
from environment_prompt import environment_description


class CurriculumEnvironment(BlindCodeEnvironment):
    def __init__(self, *args, seed=42, **kwargs):
        super().__init__(*args, **kwargs)
        self.rng = random.Random(seed)
        self.level = 0
        self.levels = []
        self.completed_levels = []
        self.feedback = {}

    def configure(self):
        self._all_pads = {k: copy.deepcopy(v) for k, v in self.objects.items()
                          if v['type'] == 'number_pad'}
        pools = {aid: [k for k, v in self._all_pads.items() if v['room'] == aid]
                 for aid in self.agents}
        for pads in pools.values():
            self.rng.shuffle(pads)
        # Pad counts and sequence length grow; both agents are required from level 3.
        for counts, owners, repeat in [((1, 0), ['A'], False),
                                       ((2, 0), ['A'] * 2, False),
                                       ((1, 1), ['A', 'B'], False),
                                       ((3, 3), ['A'] * 3 + ['B'] * 3, False),
                                       ((5, 5), ['A'] * 5 + ['B'] * 5, True)]:
            active = {aid: pools[aid][:n] for aid, n in zip(self.agents, counts)}
            self.rng.shuffle(owners)
            remaining = copy.deepcopy(active)
            sequence = [self.rng.choice(active[aid]) if repeat else remaining[aid].pop()
                        for aid in owners]
            self.levels.append((active, sequence))
        self._load_level(0)

    def _refresh_plans(self):
        for aid, agent in self.agents.items():
            agent.x, agent.y, agent.facing = self._initial_agent_states[aid]
            agent.last_move = None
            policy = agent.policy
            if policy is not None:
                for name, value in [('generated_code', None), ('_next_review_step', None),
                                    ('_last_pos', None), ('_last_action', None), ('_stall_count', 0)]:
                    if hasattr(policy, name):
                        setattr(policy, name, value)
        self._pads_inside = {}

    def _load_level(self, index):
        self.level = index + 1
        active, sequence = self.levels[index]
        self.objects = {k: v for k, v in self.objects.items() if v['type'] != 'number_pad'}
        for pads in active.values():
            for key in pads:
                self.objects[key] = copy.deepcopy(self._all_pads[key])
        self.set_sequence(sequence)
        self.progress = 0
        self._contributors = []
        self.feedback = {aid: None for aid in self.agents}
        # Object locations from past levels must not masquerade as current objects.
        self._known = {}
        self._refresh_plans()
        self._log('level_started', list(self.agents), level=self.level)

    def level_state(self):
        return {'level': self.level, 'total_levels': len(self.levels),
                'completed_levels': list(self.completed_levels),
                'sequence_length': len(self.sequence), 'resets': self.resets}

    def get_observation(self, agent_id):
        observation = super().get_observation(agent_id)
        observation['level_state'] = self.level_state()
        observation['input_feedback'] = copy.deepcopy(self.feedback.get(agent_id))
        return observation

    def _restart_attempt(self, reason, participants):
        if self.finished:
            return
        self._log('sequence_reset', sorted(set(participants)), object_id=self.vault_id,
                  reason=reason, level=self.level)
        self.resets += 1
        for aid in self.agents:
            self._notify(aid, {'type': 'attempt_reset', 'reason': reason, 'level': self.level,
                               'caused_by_you': aid in participants})
        self.progress = 0
        self._contributors = []
        self._refresh_plans()
        for aid in self.agents:
            self.feedback[aid] = {'result': 'reset', 'reason': reason,
                                  'level': self.level, 'step': self.step_count}

    def press_number_pad(self, agent_id, pad_id, contact=False):
        if self.finished or pad_id not in self.objects:
            return
        pad, agent = self.objects[pad_id], self.agents[agent_id]
        if pad['type'] != 'number_pad' or pad['room'] != agent_id:
            return
        if not contact and (agent.x-pad['x'])**2 + (agent.y-pad['y'])**2 > (pad['touch_radius'] + 1e-8)**2:
            return
        if pad_id != self.sequence[self.progress]:
            self._restart_attempt('wrong_order', [agent_id])
            self.feedback[agent_id].update(pad_id=pad_id, number=pad['number'])
            return
        self.progress += 1
        if agent_id not in self._contributors:
            self._contributors.append(agent_id)
        self.feedback[agent_id] = {'result': 'accepted', 'pad_id': pad_id,
                                   'order': self.progress, 'level': self.level,
                                   'step': self.step_count}
        self._log('number_accepted', [agent_id], object_id=pad_id,
                  number=pad['number'], order=self.progress, level=self.level)
        if self.progress != len(self.sequence):
            return
        self.completed_levels.append(self.level)
        self._log('level_completed', list(self._contributors), level=self.level)
        if self.level < len(self.levels):
            self._load_level(self.level)
        else:
            self.solved = True
            self._set_door_locked(self.objects[self.vault_id], False, 'curriculum',
                                  list(self._contributors), None)


def build_curriculum(seed=42, max_turns=600, reveal_goal=True):
    layout, _, _ = build_sequence_rooms(seed=seed, pads_per_room=5, max_turns=max_turns)
    env = CurriculumEnvironment(layout.game_map, seed=seed, max_turns=max_turns)
    env.objects = {k: copy.deepcopy(v) for k, v in layout.objects.items()
                   if v['type'] not in ('clue', 'display')}
    for aid, agent in layout.agents.items():
        env.add_agent(aid, agent.x, agent.y, facing=agent.facing)
    env.configure()
    rules = (' There are no clue or display blocks. level_state describes the current level. '
             'input_feedback reports only your own accepted input and its position, or an attempt reset; '
             'it never supplies the next correct digit. Touch a pad to input; leave and re-enter to repeat. '
             'At most one input across both agents per step. Wrong or simultaneous inputs reset the '
             'current attempt and both positions, with a 3-point penalty for participating agents. '
             'The current sequence remains the same on retry. Learning, memory and conversation persist '
             'across retries and levels. Later levels require both agents. '
             'A level change invalidates your old action code. There is a total episode turn limit.')
    goal = (' Goal: complete all five increasingly difficult levels by entering each hidden sequence '
            'in order, then unlock vault.' if reveal_goal else '')
    tasks = {aid: environment_description(aid, list(env.agents), env.game_map.map_width,
                                          env.game_map.map_height) + rules + goal
             for aid in env.agents}
    return env, tasks, [{'type': 'door_unlocked', 'door_id': env.vault_id}]
