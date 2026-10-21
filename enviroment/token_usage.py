"""Reported API token accounting and shared scoring defaults."""
import threading

TOKEN_ALLOWANCE = 50_000
# 토큰 비용이 클리어 점수를 뒤집지 않도록 작게 + 상한 (2차 실험에서 클리어한 판도 총점이 -500 아래로 떨어졌음)
TOKEN_PENALTY_PER_1000 = 0.1
TOKEN_PENALTY_CAP = -10.0
# 긴 context 감점: LLM 요청 한 번의 prompt(압축 후 실제로 보낸 context)가 START를 넘으면 그 요청마다
# (min(prompt, END) - START)^2 / DIVISOR 점을 깎음. 예: 60만 -> 10점, 80만 -> 90점, 100만 -> 250점
CONTEXT_PENALTY_START = 500_000
CONTEXT_PENALTY_END = 1_000_000
CONTEXT_PENALTY_DIVISOR = 1_000_000_000
CONTEXT_PENALTY_CAP = -10.0  # 긴 context 감점의 에이전트당 하한


def context_penalty(prompt_tokens: int, start: int = CONTEXT_PENALTY_START, end: int = CONTEXT_PENALTY_END,
                    divisor: float = CONTEXT_PENALTY_DIVISOR) -> float:
    excess = min(prompt_tokens, end) - start
    return excess * excess / divisor if excess > 0 else 0.0


class TokenUsage:
    def __init__(self):
        self.lock = threading.Lock()
        # cached_prompt_tokens: prompt_tokens 중 공급자 prompt cache에서 읽은 부분 (보고된 경우만, 비용 추정용)
        # reasoning_summary_tokens: completion_tokens 중 에이전트가 쓴 추론 요약(reasoning_summary)의 추정 토큰 수.
        # 출력 토큰 감점에서 뺌 (scoring.py)
        self.counts = dict(requests=0, prompt_tokens=0, completion_tokens=0,
                           total_tokens=0, cached_prompt_tokens=0, unreported_requests=0,
                           max_prompt_tokens=0, reasoning_summary_tokens=0)
        # 요청마다 보고된 prompt_tokens (긴 context 감점 계산용). 스냅샷에는 넣지 않음 (로그 크기)
        self.prompt_history: list[int] = []
        # 요청마다 보고된 cached_tokens (보고 안 되면 None). prompt_history와 같은 순서. 캐시가 어디서 깨지는지 보는 용도
        self.cached_history: list[int | None] = []

    def record(self, response):
        usage = getattr(response, 'usage', None)
        values = {field: getattr(usage, field, None)
                  for field in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
        reported = isinstance(values['total_tokens'], int) and not isinstance(values['total_tokens'], bool)
        if not reported:
            reported = all(isinstance(values[k], int) and not isinstance(values[k], bool)
                           for k in ('prompt_tokens', 'completion_tokens'))
            if reported:
                values['total_tokens'] = values['prompt_tokens'] + values['completion_tokens']
        with self.lock:
            self.counts['requests'] += 1
            if not reported:
                self.counts['unreported_requests'] += 1
                return
            for field, value in values.items():
                if isinstance(value, int) and not isinstance(value, bool):
                    self.counts[field] += max(0, value)
            if isinstance(values['prompt_tokens'], int) and not isinstance(values['prompt_tokens'], bool):
                self.prompt_history.append(max(0, values['prompt_tokens']))
                self.counts['max_prompt_tokens'] = max(self.counts['max_prompt_tokens'], values['prompt_tokens'])
            details = getattr(usage, 'prompt_tokens_details', None)
            cached = details.get('cached_tokens') if isinstance(details, dict) else getattr(details, 'cached_tokens', None)
            known = isinstance(cached, int) and not isinstance(cached, bool)
            if known:
                self.counts['cached_prompt_tokens'] += max(0, cached)
            if isinstance(values['prompt_tokens'], int) and not isinstance(values['prompt_tokens'], bool):
                self.cached_history.append(max(0, cached) if known else None)

    def add_reasoning_summary(self, tokens: int) -> None:
        with self.lock:
            self.counts['reasoning_summary_tokens'] += max(0, int(tokens))

    def snapshot(self):
        with self.lock:
            return dict(self.counts)


def tracker(client):
    current = getattr(client, '_maci_token_usage', None)
    if not isinstance(current, TokenUsage):
        current = TokenUsage()
        client._maci_token_usage = current
    return current
