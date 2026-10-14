"""LLM 출력 하나하나를 사람이 평가하기 위한 추출/저장 도구 (pi_logs.py의 'LLM 출력 평가' 화면이 사용).

출력은 실행의 대화 이력(<manifest>.context_archive.jsonl)에서 뽑음. assistant 메시지 하나가 LLM 응답 하나:
  - input: 그 응답 직전에 모델이 받은 마지막 입력 (context 상태 안내 메시지는 건너뜀)
  - output: 응답 본문과 도구 호출 (submit_policy_code의 코드, keep_current_code, manage_context 등)
  - result: 하네스의 도구 응답 (코드 수락/거부 등)
  - step: 그 응답이 나온 대략의 step (직전 'Simulation step result'의 step + 1)
  - summary: 에이전트가 응답마다 쓴 자기 추론 요약 (<manifest>.agent_reasoning.jsonl, tool_call_id로 연결)
  - reasoning: 프로바이더가 돌려준 숨은 추론 (있는 경우만)
사람 평가는 <manifest>.llm_ratings.<평가자>.json에 저장: 출력 id(에이전트:순번)마다 0~10점과 메모.
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

STATUS_PREFIX = 'Context management status (advisory):'
STEP_PREFIX = 'Simulation step result:'
RUBRIC = ("평가 기준 (0~10): 이 출력이 그 시점에 모델이 가진 정보로 타당한가, 과제와 상대와의 협력을 실제로 진전시키는가, "
          "코드라면 의도대로 동작할 만한가. 형식만 그럴듯한 출력에 높은 점수를 주지 마세요.")


def reasoning_path(manifest) -> Path:
    manifest = Path(manifest)
    return manifest.with_name(manifest.stem + ".agent_reasoning.jsonl")


# tool_call_id -> 그 응답의 추론 기록 (benchmark.py가 남김). 파일이 없으면(예전 실행) 빈 dict
def load_reasoning(manifest) -> dict[str, dict]:
    path = reasoning_path(manifest)
    if not path.is_file():
        return {}
    by_call = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            for call_id in record.get("tool_call_ids") or []:
                by_call.setdefault(call_id, record)
    return by_call


def archive_path(manifest) -> Path:
    manifest = Path(manifest)
    return manifest.with_name(manifest.stem + ".context_archive.jsonl")


def ratings_path(manifest, rater: str) -> Path:
    manifest = Path(manifest)
    safe = re.sub(r"[^\w.-]+", "-", rater.strip()).strip("-")
    if not safe:
        raise ValueError("평가자 이름을 입력하세요.")
    return manifest.with_name(f"{manifest.stem}.llm_ratings.{safe}.json")


def _step_of(content: str):
    try:
        return json.loads(content[len(STEP_PREFIX):])["observation"]["self"]["step"]
    except (ValueError, KeyError, TypeError):
        return None


_TEMPLATE = Path(__file__).resolve().parent / "enviroment" / "policy_template.py"


def _template_lines() -> set[str]:
    if not hasattr(_template_lines, "cache"):
        text = _TEMPLATE.read_text(encoding="utf-8") if _TEMPLATE.is_file() else ""
        _template_lines.cache = {line.strip() for line in text.splitlines() if line.strip()}
    return _template_lines.cache


def _describe_call(call: dict) -> str:
    function = call.get("function", {})
    name = function.get("name")
    try:
        args = json.loads(function.get("arguments") or "{}")
    except ValueError:
        return f"[{name}] (인자를 읽을 수 없음) {function.get('arguments')}"
    if name == "submit_policy_code":
        code = args.get("code", "")
        # 모델이 실제로 쓴 판단 영역(틀의 DECISION START~END)을 먼저 보여 주고 전체 코드는 뒤에
        match = re.search(r"DECISION START[^\n]*\n(.*?)\n[^\n]*DECISION END", code, re.S)
        if match:
            return f"[submit_policy_code] 판단 영역\n{match.group(1)}\n\n[전체 코드]\n{code}"
        # 표시가 지워졌으면 틀(policy_template.py)에 없는 줄만 먼저 모아 보여 줌
        own = [line for line in code.splitlines() if line.strip() and line.strip() not in _template_lines()]
        if own and len(own) < len(code.splitlines()):
            return "[submit_policy_code] 틀과 다른 줄\n" + "\n".join(own) + f"\n\n[전체 코드]\n{code}"
        return f"[submit_policy_code]\n{code}"
    return f"[{name}] " + json.dumps(args, ensure_ascii=False, indent=1)


# 도구 호출 하나 -> (도구 이름, 인자 dict). 인자를 읽을 수 없으면 원문을 "raw"로
def _call_args(call: dict) -> tuple[str, dict]:
    function = call.get("function", {})
    try:
        return function.get("name"), json.loads(function.get("arguments") or "{}")
    except ValueError:
        return function.get("name"), {"raw": function.get("arguments")}


def extract_outputs(manifest) -> list[dict]:
    """대화 이력의 LLM 응답 목록. 에이전트별 순서를 유지하고, id는 '에이전트:순번'."""
    path = archive_path(manifest)
    if not path.is_file():
        raise FileNotFoundError(f"대화 이력 파일이 없습니다: {path.name} (원격이면 '대화 이력 포함'으로 가져오세요)")
    outputs, last_input, last_step, counters, by_call = [], {}, {}, {}, {}
    reasoning = load_reasoning(manifest)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        agent, message = entry.get("agent"), entry.get("message") or {}
        role, content = message.get("role"), message.get("content")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        if role == "user":
            if text.startswith(STEP_PREFIX):
                step = _step_of(text)
                if step is not None:
                    last_step[agent] = step
            if not text.startswith(STATUS_PREFIX):
                last_input[agent] = text
        elif role == "assistant":
            counters[agent] = counters.get(agent, 0) + 1
            calls = message.get("tool_calls") or []
            parts = ([content] if isinstance(content, str) and content.strip() else []) + [_describe_call(c) for c in calls]
            item = {"id": f"{agent}:{counters[agent]}", "agent": agent, "index": counters[agent],
                    "step": last_step.get(agent, 0) + 1, "input": last_input.get(agent, ""),
                    "output": "\n\n".join(parts) or "(빈 응답)", "tools": [c.get("function", {}).get("name") for c in calls],
                    "calls": [_call_args(c) for c in calls], "call_ids": [c.get("id") for c in calls],
                    "summary": "", "reasoning": "", "reasoning_hidden": False, "result": []}
            found = next((reasoning[c.get("id")] for c in calls if c.get("id") in reasoning), None)
            if found:
                item["reasoning"], item["reasoning_hidden"] = found.get("reasoning", ""), bool(found.get("hidden"))
                item["summary"] = found.get("summary", "")
            outputs.append(item)
            for call in calls:
                by_call[call.get("id")] = item
        elif role == "tool":
            item = by_call.get(message.get("tool_call_id"))
            if item is not None:
                item["result"].append(text)
    return outputs


def load_ratings(manifest, rater: str) -> dict[str, dict]:
    path = ratings_path(manifest, rater)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["output_id"]: r for r in data.get("ratings", [])}


def save_rating(manifest, rater: str, output: dict, score, comment: str = "") -> None:
    """score=None이면 그 출력의 평가를 지움."""
    if score is not None and not (isinstance(score, (int, float)) and 0 <= score <= 10):
        raise ValueError("점수는 0~10이어야 합니다.")
    ratings = load_ratings(manifest, rater)
    ratings.pop(output["id"], None)
    if score is not None:
        ratings[output["id"]] = {"output_id": output["id"], "agent": output["agent"], "index": output["index"],
                                 "step": output["step"], "tools": output["tools"], "score": score,
                                 "comment": comment.strip(),
                                 "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    ordered = sorted(ratings.values(), key=lambda r: (str(r["agent"]), r["index"]))
    ratings_path(manifest, rater).write_text(json.dumps(
        {"rater": rater.strip(), "manifest": Path(manifest).name, "rubric": RUBRIC, "ratings": ordered},
        ensure_ascii=False, indent=2), encoding="utf-8")


def summary(outputs: list[dict], ratings: dict[str, dict]) -> str:
    rated = [ratings[o["id"]]["score"] for o in outputs if o["id"] in ratings]
    by_agent = {}
    for output in outputs:
        if output["id"] in ratings:
            by_agent.setdefault(output["agent"], []).append(ratings[output["id"]]["score"])
    means = "  ".join(f"{a} 평균 {sum(v) / len(v):.1f}" for a, v in sorted(by_agent.items()))
    return f"평가 {len(rated)}/{len(outputs)}" + (f"   전체 평균 {sum(rated) / len(rated):.1f}   {means}" if rated else "")
