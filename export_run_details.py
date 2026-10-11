"""Export agent messages, recorded actions, and submitted policy code from a run."""
import argparse
import json
from pathlib import Path


def export_run(path, paired_valid_steps=None):
    path = Path(path)
    records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
               if line.strip()]
    if not records:
        raise ValueError(f'No completed turns in {path}')
    condition = 'reward 공개' if records[0].get('reward_visible') else 'reward 비공개'
    header = [f'{path.name} · {condition}',
              f"모델: {records[0]['agents'][0]['model']} · 기록된 턴: {len(records)}",
              '에이전트끼리 보낸 실제 메시지 원문입니다. 에이전트의 주장과 실제 진행은 다를 수 있습니다.',
              '같은 턴의 메시지는 동시 행동에서 전송되며, 상대는 다음 턴 관찰부터 받습니다.']
    if paired_valid_steps is not None:
        header.append(f'조건 간 공통 정상 비교 구간: 1~{paired_valid_steps}턴. 이후 기록도 포함합니다.')
    messages = header + ['']
    timeline = header + ['', '행동 위치는 해당 턴 적용 후 위치입니다. 이벤트는 실제 환경 판정입니다.', '']
    action_records = []
    codes = {}
    message_count = 0
    for record in records:
        step = record['step']
        level = record.get('world', {}).get('level_state', {}).get('level', '?')
        timeline.append(f'===== 턴 {step} · 단계 {level} =====')
        for message in record.get('messages', []):
            message_count += 1
            sender, receiver = message.get('from', '?'), message.get('receiver_id', '?')
            label = f"[턴 {step} · 단계 {level} · {sender} → {receiver} · {message.get('type', 'text')}]"
            messages.extend([label, str(message.get('content', '')), ''])
            timeline.extend([label, str(message.get('content', ''))])
        for agent in record['agents']:
            aid, decision = agent['agent'], agent['decision']
            code = agent.get('generated_code')
            error = decision.get('policy_error')
            origin = ('error_fallback' if error else 'generated_policy' if code else 'direct_action')
            action_records.append({'step': step, 'level': level, 'agent': aid, 'origin': origin,
                                   'requested_action': decision.get('action'),
                                   'final_action': decision.get('final_action'),
                                   'position_after_action': agent['position'],
                                   'facing_after_action': agent.get('facing'),
                                   'policy_error': error, 'generated_code': code})
            timeline.append(f"{aid} · {origin} · 위치={agent['position']} · 방향={agent.get('facing')}")
            timeline.append(json.dumps(decision.get('final_action'), ensure_ascii=False))
            if error:
                timeline.append('API/정책 오류: ' + error.strip().splitlines()[-1])
            if code:
                codes.setdefault((aid, code), []).append(step)
        for event in record.get('events', []):
            timeline.append('환경 이벤트: ' + json.dumps(event, ensure_ascii=False))
        timeline.append('')
    code_lines = [f'{path.name} · 기록된 Python 정책 코드', '']
    if not codes:
        code_lines.extend(['이 실행에서 기록된 generated_code는 모든 턴에서 None입니다.',
                           'LLM은 hybrid 정책의 직접 JSON 행동 모드를 사용했습니다.',
                           'API 오류가 발생한 턴의 noop은 모델이 생성한 코드가 아니라 오류 폴백입니다.',
                           '전체 행동은 같은 이름의 .actions.jsonl, 메시지는 .messages.txt에 있습니다.'])
    for (aid, code), steps in codes.items():
        code_lines.extend([f"===== 에이전트 {aid} · 최초 턴 {steps[0]} · 사용 턴 {steps} =====", code, ''])
    outputs = {'.messages.txt': '\n'.join(messages), '.timeline.txt': '\n'.join(timeline),
               '.code.txt': '\n'.join(code_lines),
               '.actions.jsonl': '\n'.join(json.dumps(a, ensure_ascii=False) for a in action_records) + '\n'}
    for suffix, content in outputs.items():
        path.with_suffix(suffix).write_text(content, encoding='utf-8')
    return {'run': path.name, 'messages': message_count, 'agent_actions': len(action_records),
            'unique_agent_codes': len(codes), 'outputs': [str(path.with_suffix(s)) for s in outputs]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', nargs='+')
    parser.add_argument('--paired-valid-steps', type=int)
    args = parser.parse_args()
    for path in args.runs:
        print(json.dumps(export_run(path, args.paired_valid_steps), ensure_ascii=True))


if __name__ == '__main__':
    main()
