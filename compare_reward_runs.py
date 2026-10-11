"""Summarize a paired reward-visibility experiment from benchmark traces."""
import argparse
import collections
import json
from pathlib import Path


def summarize(path, through_step=None):
    path = Path(path)
    events = collections.Counter()
    actions = collections.Counter()
    completion_steps = {}
    last = None
    errors = 0
    messages = 0
    progress = 0
    first_error_steps = {}
    first = None
    with path.open(encoding='utf-8') as source:
        for line in source:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # A live writer may not have finished its last line yet.
                continue
            if through_step is not None and record['step'] > through_step:
                break
            first = first or record
            last = record
            for event in record.get('events', []):
                events[event['type']] += 1
                if event['type'] in ('level_started', 'sequence_reset'):
                    progress = 0
                elif event['type'] == 'number_accepted':
                    progress = event['order']
                if event['type'] == 'level_completed':
                    completion_steps[str(event['level'])] = event['step']
            for agent in record['agents']:
                decision = agent['decision']
                actions[(decision.get('final_action') or {}).get('type', 'missing')] += 1
                errors += bool(decision.get('policy_error'))
                if decision.get('policy_error'):
                    first_error_steps.setdefault(agent['agent'], record['step'])
            messages += len(record.get('messages', []))
    if last is None:
        return {'path': str(path), 'status': 'no_completed_steps'}
    score_file = path.with_suffix('.score.json')
    termination_file = path.with_suffix('.termination.json')
    termination = (json.loads(termination_file.read_text(encoding='utf-8'))
                   if termination_file.exists() else None)
    score = (json.loads(score_file.read_text(encoding='utf-8'))
             if score_file.exists() and through_step is None else last['score'])
    usage = {aid: data.get('token_usage', {}) for aid, data in score['agents'].items()}
    return {
        'path': str(path), 'status': ('stopped' if termination else
                                    'finished' if score_file.exists() else 'running'),
        'termination': termination, 'through_step': through_step,
        'model': first['agents'][0]['model'], 'seed': first['map_seed'],
        'reward_visible': first['reward_visible'], 'steps': last['step'],
        'cleared': last['cleared'], 'failure': last['failure'],
        'levels': last['world'].get('level_state'), 'level_completion_steps': completion_steps,
        'current_attempt_progress': progress,
        'score': score['total'], 'individual_score': score['individual_total'],
        'team_score': score['team']['score'],
        'agent_scores': {aid: data['score'] for aid, data in score['agents'].items()},
        'token_penalties': {aid: data.get('token_penalty', 0) for aid, data in score['agents'].items()},
        'token_usage': usage,
        'total_token_usage': {key: sum(data.get(key, 0) for data in usage.values())
                              for key in ('requests', 'prompt_tokens', 'completion_tokens', 'total_tokens',
                                          'unreported_requests')},
        'messages': messages, 'policy_error_agent_steps': errors,
        'first_policy_error_steps': first_error_steps,
        'events': dict(events), 'actions': dict(actions),
        'code_checks': score.get('code_checks', {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('visible')
    parser.add_argument('hidden')
    parser.add_argument('--out')
    parser.add_argument('--through-step', type=int)
    args = parser.parse_args()
    visible, hidden = summarize(args.visible, args.through_step), summarize(args.hidden, args.through_step)
    result = {'visible': visible, 'hidden': hidden,
              'limitations': ['One paired seed; not a statistically reliable effect estimate.',
                              'Correctness and level feedback remain available in both conditions.',
                              'API responses may vary even with temperature zero.']}
    if visible.get('seed') != hidden.get('seed') or visible.get('model') != hidden.get('model'):
        raise ValueError('The model and map seed must match for this comparison.')
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
