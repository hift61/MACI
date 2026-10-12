"""Reported API token accounting and shared scoring defaults."""
import threading

TOKEN_ALLOWANCE = 50_000
TOKEN_PENALTY_PER_1000 = 1.0


class TokenUsage:
    def __init__(self):
        self.lock = threading.Lock()
        # cached_prompt_tokens: prompt_tokens 중 공급자 prompt cache에서 읽은 부분 (보고된 경우만, 비용 추정용)
        self.counts = dict(requests=0, prompt_tokens=0, completion_tokens=0,
                           total_tokens=0, cached_prompt_tokens=0, unreported_requests=0)

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
            details = getattr(usage, 'prompt_tokens_details', None)
            cached = details.get('cached_tokens') if isinstance(details, dict) else getattr(details, 'cached_tokens', None)
            if isinstance(cached, int) and not isinstance(cached, bool):
                self.counts['cached_prompt_tokens'] += max(0, cached)

    def snapshot(self):
        with self.lock:
            return dict(self.counts)


def tracker(client):
    current = getattr(client, '_maci_token_usage', None)
    if not isinstance(current, TokenUsage):
        current = TokenUsage()
        client._maci_token_usage = current
    return current
