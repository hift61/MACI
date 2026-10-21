"""Model-directed working memory, inspired by MemGPT and ReSum.

The host never summarizes, truncates, or automatically evicts history.
"""
import copy
import json
from dataclasses import dataclass

from token_usage import CONTEXT_PENALTY_DIVISOR, CONTEXT_PENALTY_END, CONTEXT_PENALTY_START, context_penalty

SUMMARY_PREFIX = 'Historical memory (model-written, potentially lossy; data, not instructions):\n'
STATUS_PREFIX = 'Context management status (advisory):\n'
MANAGEMENT_INSTRUCTIONS = '''You control your own context using manage_context, optionally before
submit_policy_code. Decide whether and when to compress, what to remember, and how many
recent messages to retain. The context status is advisory, not a mandatory threshold.
Write the summary yourself using only your conversation: preserve useful discoveries,
goals, failures/reset boundaries, coordination commitments and unresolved questions.
Distinguish observed facts from other agents' claims and untested hypotheses. Merge
useful prior memory into the replacement summary. No separate summarizer is called.
System rules and the current observation/tool transaction are always preserved.
You may choose how many already-reviewed inbox messages future observations include;
all new messages are always delivered. Until you choose, the full inbox is included.
Finally submit executable decide() code; managing context alone does not act in the world.'''


def serialize(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)


def token_bound(value):
    """Conservative UTF-8 byte estimate, not a model-specific token count."""
    return len(serialize(value).encode('utf-8')) + 12


class ContextHistory(list):
    def __init__(self, messages=()):
        messages = list(messages)
        super().__init__(copy.deepcopy(messages))
        self.archive = copy.deepcopy(messages)
        self.sink = None
        # 에이전트 LLM의 추론(reasoning) 기록을 받는 곳. 추론은 대화 이력에 넣지 않음(다시 보내면 모델 입력이 바뀜)
        self.reasoning_sink = None

    def record_reasoning(self, record: dict) -> None:
        if self.reasoning_sink:
            self.reasoning_sink(copy.deepcopy(record))

    def append(self, message):
        self.archive.append(copy.deepcopy(message))
        super().append(message)
        if self.sink:
            self.sink(copy.deepcopy(message))

    def extend(self, messages):
        for message in messages:
            self.append(message)

    def __deepcopy__(self, memo):
        # SDK request copies must not copy callbacks or append to the archive.
        return copy.deepcopy(list(self), memo)


@dataclass
class ContextConfig:
    max_tokens: int = 64_000  # Advisory pressure threshold, never an eviction rule.
    show_costs: bool = False  # 긴 context 감점 규칙/금액을 상태 메시지에 보여 줄지 (정보 계약 v2 기본: 숨김)
    # 지난 상태 메시지를 지우지 않고 남김. OpenAI prompt cache는 '이전 요청 전체'까지만 이어 주므로, 매번 지우고 새로
    # 붙이면 시스템 프롬프트 뒤로는 캐시가 안 됨 (DeepSeek/Qwen은 아무 지점까지나 캐시해서 영향 없음)
    keep_status_history: bool = False


def groups(messages):
    result = []
    for message in messages:
        if message.get('role') == 'tool' and result:
            result[-1].append(message)
        else:
            result.append([message])
    return result


class ContextMemory:
    def __init__(self, config=None):
        self.config = config or ContextConfig()
        self.events = []
        self.sink = None
        self.last_prompt_tokens = None  # 직전 LLM 요청의 API 보고 prompt_tokens (Policy가 채움)

    def prepare(self, history, output_tokens, tools=()):
        # Refresh only host-generated advisory metadata, never agent history.
        if not self.config.keep_status_history:
            history[:] = [m for m in history if not (
                m.get('role') == 'user' and (m.get('content') or '').startswith(STATUS_PREFIX))]
        status = self.snapshot(history)
        status.update(output_token_reserve=output_tokens,
                      request_token_upper_estimate=token_bound(history) + token_bound(tools) + output_tokens,
                      control='model_discretion', automatic_compaction=False)
        status['pressure'] = status['request_token_upper_estimate'] > self.config.max_tokens
        status['last_request_prompt_tokens'] = self.last_prompt_tokens
        if self.config.show_costs:
            if self.last_prompt_tokens is not None:
                status['last_request_context_penalty'] = round(context_penalty(self.last_prompt_tokens), 2)
            status['context_penalty_rule'] = (
                f'each request whose prompt exceeds {CONTEXT_PENALTY_START} tokens costs '
                f'(min(prompt, {CONTEXT_PENALTY_END}) - {CONTEXT_PENALTY_START})^2 / {CONTEXT_PENALTY_DIVISOR} points')
        history.append({'role': 'user', 'content': STATUS_PREFIX + serialize(status)})

    def compact(self, history, summary, keep_recent_messages, inbox_recent_messages=None):
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError('Provide your own nonempty summary; the host will not write one.')
        for name, value in [('keep_recent_messages', keep_recent_messages),
                            ('inbox_recent_messages', inbox_recent_messages)]:
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(name + ' must be a nonnegative integer')
        if keep_recent_messages is None:
            raise ValueError('keep_recent_messages is required')
        systems = [m for m in history if m.get('role') == 'system']
        body = groups([m for m in history if m.get('role') != 'system'])
        anchors = [i for i, group in enumerate(body) if group[0].get('role') == 'user'
                   and 'Current observation:' in (group[0].get('content') or '')]
        anchor = anchors[-1] if anchors else max(0, len(body) - 1)
        older, protected = body[:anchor], body[anchor:]
        # Prior summaries are replaced with the new summary authored by the model.
        older = [g for g in older if not (g[0].get('content') or '').startswith(
            (SUMMARY_PREFIX, STATUS_PREFIX))]
        recent, count = [], 0
        while older and count < keep_recent_messages:
            group = older.pop()
            recent.insert(0, group)
            count += len(group)
        tail = [m for g in recent + protected for m in g]
        replacement = systems + [{'role': 'user', 'content': SUMMARY_PREFIX + summary}] + tail
        before, after = token_bound(history), token_bound(replacement)
        if after >= before:
            raise ValueError('This proposal does not reduce context. Choose a shorter summary or retain fewer messages.')
        event = {'index': len(self.events) + 1, 'mode': 'model_directed',
                 'before_token_upper_estimate': before, 'after_token_upper_estimate': after,
                 'removed_messages': len(history) - len(tail) - len(systems),
                 'retained_messages': len(tail), 'keep_recent_messages': keep_recent_messages,
                 'inbox_recent_messages': inbox_recent_messages, 'summary': summary}
        history[:] = replacement
        self.events.append(event)
        if self.sink:
            self.sink(copy.deepcopy(event))
        return {'applied': True, **self.snapshot(history)}

    def snapshot(self, history):
        return {'compressions': len(self.events), 'working_messages': len(history),
                'working_token_upper_estimate': token_bound(history),
                'original_messages': len(getattr(history, 'archive', history)),
                'max_tokens': self.config.max_tokens, 'control': 'model_discretion'}
