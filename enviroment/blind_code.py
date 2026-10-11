"""A no-hint control: the secret is independent of all visible state."""
import copy
import secrets

from environment_prompt import environment_description
from sequence_rooms import SequenceRoomsEnvironment, build_sequence_rooms


class BlindCodeEnvironment(SequenceRoomsEnvironment):
    CODE_LENGTH = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.submitted = []
        self.submitted_by = []
        self._initial_agent_states = {}

    def add_agent(self, *args, **kwargs):
        agent = super().add_agent(*args, **kwargs)
        self._initial_agent_states[agent.agent_id] = (agent.x, agent.y, agent.facing)
        return agent

    def _restart_attempt(self, reason, participants):
        self._log('sequence_reset', sorted(set(participants)), object_id=self.vault_id,
                  reason=reason)
        self.resets += 1
        self.progress = 0
        self.submitted = []
        self.submitted_by = []
        self._contributors = []
        self._pads_inside = {}
        for aid, agent in self.agents.items():
            agent.x, agent.y, agent.facing = self._initial_agent_states[aid]
            agent.last_move = None
            agent.memory = {}
            # Preserve conversation, inbox and token counters so mistakes can be
            # learned from, but let the LLM choose a fresh plan next turn.
            policy = agent.policy
            if policy is not None and hasattr(policy, 'generated_code'):
                policy.generated_code = None
                policy._next_review_step = None
                policy._last_pos = None
                policy._last_action = None
                policy._stall_count = 0

    def press_number_pad(self, agent_id, pad_id, contact=False):
        if self.finished:
            return
        agent, pad = self.agents[agent_id], self.objects[pad_id]
        if pad['room'] != agent_id:
            return
        if not contact and (agent.x-pad['x'])**2 + (agent.y-pad['y'])**2 > pad['touch_radius']**2:
            return
        self.submitted.append(pad_id)
        self.submitted_by.append(agent_id)
        self.progress = len(self.submitted)
        self._log('number_submitted', [agent_id], object_id=pad_id, number=pad['number'])
        if agent_id not in self._contributors:
            self._contributors.append(agent_id)
        # No prefix oracle: every partial submission has identical effects.
        if self.progress < self.CODE_LENGTH:
            return
        cooperative = all(self.submitted_by.count(aid) == 5 for aid in self.agents)
        if self.submitted != self.sequence or not cooperative:
            self._restart_attempt('incorrect_code', self.submitted_by)
            return
        self.solved = True
        self._log('sequence_completed', list(self._contributors))
        self._set_door_locked(self.objects[self.vault_id], False, 'blind_code',
                              list(self._contributors), None)

    def _reset_sequence(self, contacts, reason):
        self._restart_attempt('invalid_submission', [aid for aid, _ in contacts])


def build_blind_code(seed=42, max_turns=150, reveal_goal=True):
    layout, _, _ = build_sequence_rooms(seed=seed, pads_per_room=5,
                                       presses_per_room=5, max_turns=max_turns)
    env = BlindCodeEnvironment(layout.game_map, max_turns=max_turns)
    env.objects = {oid: copy.deepcopy(obj) for oid, obj in layout.objects.items()
                   if obj['type'] not in ('clue', 'display')}
    for aid, agent in layout.agents.items():
        env.add_agent(aid, agent.x, agent.y, facing=agent.facing)
    pads = {aid: [oid for oid, obj in env.objects.items()
                  if obj['type'] == 'number_pad' and obj['room'] == aid]
            for aid in env.agents}
    # Each agent contributes five digits; the ownership order is also secret.
    # Independent of layout seed: C(10,5) * 5**10 possible balanced codes.
    owners = [aid for aid in env.agents for _ in range(5)]
    secrets.SystemRandom().shuffle(owners)
    env.set_sequence([secrets.choice(pads[aid]) for aid in owners])
    goal = (" Goal: unlock door 'vault' by submitting a 10-digit code using the number pads. "
            "Enter a pad's touch_radius to submit its number; leave and re-enter for repeated digits. "
            "Submit at most one digit per step across both agents. "
            "Both agents must participate: each supplies exactly five digits from its own room. "
            "Only a complete submission receives a correctness result. "
            "A wrong full code or simultaneous inputs reset the attempt and both agents' position, "
            "facing and action memory. Participating agents lose 3 points per reset. "
            "You may retry until the episode's turn limit; the secret stays the same."
            if reveal_goal else '')
    tasks = {aid: environment_description(aid, list(env.agents),
                                         env.game_map.map_width, env.game_map.map_height)
                  + " There are no clue blocks or display/update blocks in this environment. "
                    "No hints, prefix correctness, or correct-order progress updates are provided."
                  + goal
             for aid in env.agents}
    return env, tasks, [{'type': 'door_unlocked', 'door_id': env.vault_id}]
