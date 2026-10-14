"""판정기(judge)에게 줄 '판단 시점' 묶음을 실행 기록에서 만듦 (maci_judge.py --unit anchor가 사용).

매 step을 판정하는 대신, 에이전트에게 바깥 맥락이 바뀐 시점(기준점)마다 한 번 판정함:
  - 기준점: 상대 메시지 도착, 실패 알림(sync_fail, 패널 초기화, 막힘 등), 단계 시작, 메시지/환경 변화로 인한 재호출.
    이런 변화가 거의 없던 에이전트는 자기 LLM 응답 시점에서 고르게 골라 최소 개수를 채움 (소통하지 않은 것도 판정 대상)
  - 묶음 하나 = 그 시점의 계기 + 그 직후 LLM 응답(코드 변경분, keep, context 요약) + 이어진 행동
    + 그 시점의 memory와 가장 최근 context 요약 + 그 전에 돌던 코드
    + 기준점 '이전' 조각 중 응답과 가장 관련 있는 것 상위 k개 (임베딩 유사도, 실패하면 단어 기반 유사도)
조각의 단위는 LLM 응답(턴), memory 변화, 메시지, step별 이벤트. 응답마다 에이전트의 추론이
<manifest>.agent_reasoning.jsonl에 있으면 그 턴 앞에 붙임 (프로바이더가 돌려준 경우만: luna는 요약, GLM은 원문,
Haiku는 도구 호출을 강제하는 하네스에서는 추론이 없음). 없으면 코드 주석, manage_context 요약, memory, 메시지가 추론의 흔적임.
판정 대상 에이전트가 알 수 있었던 것만 넣음: 상대의 코드/memory/요약은 넣지 않고, 상대가 보낸 메시지만 넣음.

    python judge_context.py run/s05_lossy_sync.jsonl [--retrieval lexical]   # 묶음을 만들어 <이름>.judge_bundles.json에 저장
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

import judge_agreement
import llm_outputs

# 기준점이 되는 이벤트 (그 이벤트에 이름이 오른 에이전트에게)
ANCHOR_EVENTS = {"sync_fail", "keypad_reset", "keypad_denied", "keypad_attempt", "level_started", "pickup_blocked",
                 "move_blocked", "push_too_weak", "zone_overloaded", "cargo_spoiled", "message_lost",
                 "message_blocked", "bonus_expired", "block_stuck"}
# 조각/계기 설명에서 뺄 이벤트 (너무 잦고 판단과 무관)
QUIET_EVENTS = {"object_seen", "item_spawned"}
# 이 계기는 앞 기준점에 합치지 않고 새 기준점을 엶 (실패/단계 변화에 대한 반응을 따로 봐야 하므로)
STRONG_EVENTS = {"sync_fail", "keypad_reset", "level_started", "cargo_spoiled", "message_lost"}
DEFAULT_EMBED_MODEL = "openai/text-embedding-3-small"
EMBED_CHARS = 6000


# ---------------------------------------------------------------- 조각 만들기

def _decision_region(code: str) -> str:
    match = re.search(r"DECISION START[^\n]*\n(.*?)\n[^\n]*DECISION END", code, re.S)
    return match.group(1) if match else code


def _code_change(previous: str | None, code: str, max_lines: int = 60) -> str:
    if not previous:
        lines = _decision_region(code).splitlines()
        body = "\n".join(lines[:max_lines]) + ("\n..." if len(lines) > max_lines else "")
        return "first policy code (decision part):\n" + body
    diff = [l for l in difflib.unified_diff(_decision_region(previous).splitlines(),
                                            _decision_region(code).splitlines(), lineterm="", n=0)
            if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    if not diff:
        return "resubmitted the same decision code"
    return "code change:\n" + "\n".join(diff[:max_lines]) + ("\n..." if len(diff) > max_lines else "")


def _short(value, limit=300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


def _event_text(event: dict) -> str:
    fields = {k: v for k, v in event.items() if k not in ("step", "type", "agent_ids")}
    return f"{event['type']}({', '.join(event.get('agent_ids') or [])}) {_short(fields, 160) if fields else ''}".strip()


def _action_text(action) -> str:
    if not action:
        return "none"
    fields = {k: v for k, v in action.items() if k not in ("type", "memory", "recheck_after")}
    return action.get("type", "?") + (f" {_short(fields, 120)}" if fields else "")


def load_run(manifest) -> dict:
    """실행 기록을 에이전트별 조각/행동/기준점 재료로 정리."""
    manifest = Path(manifest)
    records = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    agents = [a["agent"] for a in records[0]["agents"]] if records else []
    chunks = {a: [] for a in agents}      # 그 에이전트가 알 수 있었던 조각 (step, kind, text)
    actions = {a: {} for a in agents}     # step -> 실제 실행된 행동
    memory = {a: {} for a in agents}      # step -> memory
    triggers = {a: {} for a in agents}    # step -> [계기 설명]
    strong = {a: set() for a in agents}   # 새 기준점을 여는 step
    tasks = (records[0].get("task") or {}) if records else {}

    previous_code, summaries = {}, {a: [] for a in agents}
    for output in llm_outputs.extract_outputs(manifest):
        agent, step = output["agent"], output["step"]
        if agent not in chunks:
            continue
        parts = []
        if output.get("reasoning"):
            parts.append("agent reasoning: " + _short(output["reasoning"], 2500))
        elif output.get("reasoning_hidden"):
            parts.append("agent reasoning: (hidden by the provider)")
        for name, args in output.get("calls", []):
            if name == "submit_policy_code":
                code = args.get("code", "")
                parts.append(_code_change(previous_code.get(agent), code))
                previous_code[agent] = code
            elif name == "manage_context":
                parts.append("context summary written by the agent: " + _short(args.get("summary", args), 1500))
                summaries[agent].append((step, args.get("summary", "")))
            else:
                parts.append(f"{name}: {_short(args, 400)}")
        rejected = [r for r in output.get("result", []) if '"accepted": false' in r]
        if rejected:
            parts.append("harness rejected it: " + _short(rejected[0], 300))
        chunks[agent].append({"step": step, "kind": "turn", "text": "\n".join(parts) or "(empty response)"})

    for record in records:
        step = record["step"]
        for message in record.get("messages") or []:
            sender, receiver = message.get("from"), message.get("receiver_id")
            text = f"message {sender} -> {receiver}: {_short(message.get('content'), 500)}"
            for agent in {sender, receiver} & set(agents):
                chunks[agent].append({"step": step, "kind": "message", "text": text})
            if receiver in triggers:
                triggers[receiver].setdefault(step, []).append(f"received {text}")
        by_agent: dict[str, list[str]] = {}
        for event in record.get("events") or []:
            if event["type"] in QUIET_EVENTS:
                continue
            for agent in set(event.get("agent_ids") or []) & set(agents):
                by_agent.setdefault(agent, []).append(_event_text(event))
                if event["type"] in ANCHOR_EVENTS:
                    triggers[agent].setdefault(step, []).append(_event_text(event))
                    if event["type"] in STRONG_EVENTS:
                        strong[agent].add(step)
        for agent, texts in by_agent.items():
            chunks[agent].append({"step": step, "kind": "events", "text": f"step {step} events: " + "; ".join(texts)})
        for agent_record in record["agents"]:
            agent = agent_record["agent"]
            decision = agent_record.get("decision") or {}
            actions[agent][step] = decision.get("final_action")
            mem = (decision.get("action") or {}).get("memory")
            if mem is not None:
                memory[agent][step] = mem
            if decision.get("message_interrupt"):
                triggers[agent].setdefault(step, []).append("re-asked because a message arrived")
            replan = decision.get("replan") or {}
            if "environment" in str(replan.get("reason", "")).lower():
                triggers[agent].setdefault(step, []).append("re-asked because the surroundings changed")

    for agent in agents:  # memory가 바뀐 시점마다 조각 하나
        last = None
        for step in sorted(memory[agent]):
            mem = memory[agent][step]
            if mem != last:
                changed = {k: v for k, v in mem.items() if not isinstance(last, dict) or last.get(k) != v}
                chunks[agent].append({"step": step, "kind": "memory", "text": "memory update: " + _short(changed, 600)})
                last = mem
        chunks[agent].sort(key=lambda c: (c["step"], c["kind"]))
    return {"manifest": str(manifest), "agents": agents, "chunks": chunks, "actions": actions, "memory": memory,
            "triggers": triggers, "strong": strong, "tasks": tasks, "summaries": summaries, "steps": records[-1]["step"] if records else 0}


# ---------------------------------------------------------------- 기준점

def select_anchors(triggers: dict[int, list[str]], merge_window: int = 4, max_anchors: int = 12,
                   strong: set | None = None) -> list[dict]:
    """기준점 첫 step에서 merge_window step 안의 계기는 하나로 합침. 단 strong step(실패, 단계 시작 등)은 새 기준점을 엶.
    너무 많으면 고르게 max_anchors개만."""
    anchors, strong = [], strong or set()
    for step in sorted(triggers):
        if anchors and step - anchors[-1]["step"] < merge_window and step not in strong:
            anchors[-1]["trigger"] += triggers[step]
            continue
        anchors.append({"step": step, "trigger": list(triggers[step])})
    for anchor in anchors:  # 같은 계기가 반복되면 횟수로 줄임
        counts = Counter(anchor["trigger"])
        anchor["trigger"] = [t if n == 1 else f"{t} (x{n})" for t, n in counts.items()][:12]
    if len(anchors) > max_anchors:
        idx = sorted({round(i * (len(anchors) - 1) / (max_anchors - 1)) for i in range(max_anchors)})
        anchors = [anchors[i] for i in idx]
    return anchors


# ---------------------------------------------------------------- 유사도

def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


class LexicalSimilarity:
    """단어(물체 id, 메시지 단어) TF-IDF 코사인. 외부 호출 없음"""

    def __init__(self, texts: list[str]):
        docs = [Counter(_tokens(t)) for t in texts]
        df = Counter(w for d in docs for w in d)
        self.idf = {w: math.log((1 + len(docs)) / (1 + n)) + 1 for w, n in df.items()}

    def vector(self, text: str) -> dict:
        tf = Counter(_tokens(text))
        vec = {w: c * self.idf.get(w, 1.0) for w, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {w: v / norm for w, v in vec.items()}

    def score(self, query: str, texts: list[str]) -> list[float]:
        q = self.vector(query)
        return [sum(q.get(w, 0.0) * v for w, v in self.vector(t).items()) for t in texts]


class EmbeddingSimilarity:
    """OpenAI 호환 /embeddings (기본: OpenRouter의 text-embedding-3-small). 결과는 텍스트 해시로 파일에 캐시"""

    def __init__(self, client, model: str = DEFAULT_EMBED_MODEL, cache_path: Path | None = None):
        self.client, self.model, self.cache_path = client, model, cache_path
        self.cache: dict[str, list[float]] = {}
        if cache_path and cache_path.is_file():
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if data.get("model") == model:
                self.cache = data.get("vectors", {})

    def _embed(self, texts: list[str]) -> list[list[float]]:
        keys = [hashlib.sha1(t[:EMBED_CHARS].encode("utf-8")).hexdigest() for t in texts]
        missing = sorted({k: t for k, t in zip(keys, texts) if k not in self.cache}.items())
        for start in range(0, len(missing), 64):
            batch = missing[start:start + 64]
            response = self.client.embeddings.create(model=self.model, input=[t[:EMBED_CHARS] for _, t in batch])
            for (key, _), item in zip(batch, response.data):
                self.cache[key] = [round(x, 5) for x in item.embedding]
        if missing and self.cache_path:
            self.cache_path.write_text(json.dumps({"model": self.model, "vectors": self.cache}), encoding="utf-8")
        return [self.cache[k] for k in keys]

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        vectors = self._embed([query] + texts)
        q = vectors[0]
        qn = math.sqrt(sum(x * x for x in q)) or 1.0
        return [sum(a * b for a, b in zip(q, v)) / (qn * (math.sqrt(sum(x * x for x in v)) or 1.0))
                for v in vectors[1:]]


# ---------------------------------------------------------------- 묶음

def _compress_actions(actions: dict[int, dict], start: int, end: int) -> list[str]:
    runs = []
    for step in range(start, end + 1):
        if step not in actions:
            continue
        text = _action_text(actions[step])
        if runs and runs[-1][2] == text and runs[-1][1] == step - 1:
            runs[-1][1] = step
        else:
            runs.append([step, step, text])
    return [f"step {a}{'' if a == b else f'-{b}'}: {t}" for a, b, t in runs]


def _with_routine_anchors(anchors: list[dict], turns: list[dict], min_anchors: int) -> list[dict]:
    """바깥 변화가 거의 없던 에이전트(메시지도 실패도 없음)도 판정받도록, 기준점이 min_anchors개보다 적으면
    그 에이전트의 LLM 응답 시점에서 고르게 골라 채움. 상대와 소통하지 않은 것 자체가 판정 대상이므로"""
    taken = {a["step"] for a in anchors}
    candidates = [t["step"] for t in turns if t["step"] not in taken]
    need = min(min_anchors - len(anchors), len(candidates))
    if need <= 0:
        return anchors
    picks = sorted({candidates[round(i * (len(candidates) - 1) / max(1, need - 1))] for i in range(need)})
    routine = [{"step": s, "trigger": ["routine LLM re-check (no new message or failure for this agent)"]}
               for s in picks]
    return sorted(anchors + routine, key=lambda a: a["step"])


def build_bundles(manifest, similarity_factory=None, top_k: int = 4, merge_window: int = 4, max_anchors: int = 12,
                  horizon: int = 30, action_window: int = 12, agent_filter: str | None = None,
                  min_anchors: int = 4) -> list[dict]:
    """similarity_factory(texts) -> .score(query, texts) 객체. None이면 단어 기반."""
    run = load_run(manifest)
    bundles = []
    for agent in run["agents"]:
        if agent_filter and agent != agent_filter:
            continue
        chunks = run["chunks"][agent]
        turns = [c for c in chunks if c["kind"] == "turn"]
        similarity = (similarity_factory or LexicalSimilarity)([c["text"] for c in chunks])
        anchors = select_anchors(run["triggers"][agent], merge_window, max_anchors, run["strong"][agent])
        for anchor in _with_routine_anchors(anchors, turns, min_anchors):
            step = anchor["step"]
            running = next((t for t in reversed(turns) if t["step"] < step), None)
            response = [t for t in turns if step <= t["step"] <= step + horizon][:2]
            memory_steps = [s for s in run["memory"][agent] if s <= step]
            summary = next((s for s in reversed(run["summaries"][agent]) if s[0] <= step), None)
            earlier = [c for c in chunks if c["step"] < step and c is not running]
            query = "\n".join(anchor["trigger"] + [t["text"] for t in response])
            scores = similarity.score(query, [c["text"] for c in earlier]) if earlier else []
            ranked = sorted(zip(scores, range(len(earlier))), reverse=True)[:top_k]
            retrieved = [dict(earlier[i], similarity=round(s, 3)) for s, i in sorted(ranked, key=lambda x: x[1])]
            bundles.append({
                "agent": agent, "step": step, "task": run["tasks"].get(agent, ""), "trigger": anchor["trigger"],
                "memory": run["memory"][agent][memory_steps[-1]] if memory_steps else None,
                "summary": {"step": summary[0], "text": summary[1]} if summary else None,
                "running_code": running, "response": response,
                "actions": _compress_actions(run["actions"][agent], step, step + action_window),
                "retrieved": retrieved,
            })
    bundles.sort(key=lambda b: (b["step"], b["agent"]))
    return bundles


def render(bundle: dict, budget: int | None = None) -> str:
    """판정기에게 보낼 글. budget(글자 수)이 있으면 긴 칸을 그 길이로 자름"""
    def cut(text):
        text = text or ""
        return text if budget is None or len(text) <= budget else text[:budget] + "\n...(trimmed)"

    lines = [f"=== AGENT {bundle['agent']} AT STEP {bundle['step']} ===", f"Task given to the agent: {bundle.get('task', '')}", "",
             "=== WHAT CHANGED (trigger) ===", *bundle["trigger"], "",
             "=== AGENT'S MEMORY AT THIS POINT ===", cut(_short(bundle["memory"], 3000)), ""]
    if bundle["summary"]:
        lines += [f"=== AGENT'S LATEST CONTEXT SUMMARY (written at step {bundle['summary']['step']}) ===",
                  cut(bundle["summary"]["text"]), ""]
    lines += ["=== EARLIER CONTEXT THE AGENT HAD (most relevant pieces, oldest first) ==="]
    lines += [f"[step {c['step']}, {c['kind']}] {cut(c['text'])}" for c in bundle["retrieved"]] or ["(none)"]
    lines += ["", "=== POLICY RUNNING BEFORE THE TRIGGER ==="]
    lines += [f"[step {bundle['running_code']['step']}] {cut(bundle['running_code']['text'])}"
              if bundle["running_code"] else "(none yet)"]
    lines += ["", "=== AGENT'S RESPONSE (LLM turns after the trigger) ==="]
    lines += [f"[step {t['step']}] {cut(t['text'])}" for t in bundle["response"]] or [
        "(no new LLM turn: the existing policy code kept running)"]
    lines += ["", "=== ACTIONS ACTUALLY EXECUTED FROM THE TRIGGER ON ===", *bundle["actions"]]
    return "\n".join(lines)


def make_similarity(kind: str, manifest, client=None, embed_model: str = DEFAULT_EMBED_MODEL):
    if kind == "lexical" or client is None:
        return LexicalSimilarity
    cache = Path(manifest).with_name(Path(manifest).stem + ".judge_embeddings.json")
    embedder = EmbeddingSimilarity(client, embed_model, cache)
    return lambda texts: embedder


def bundles_path(manifest) -> Path:
    manifest = Path(manifest)
    return manifest.with_name(manifest.stem + ".judge_bundles.json")


def load_or_build_bundles(manifest, client=None, embed_model: str = DEFAULT_EMBED_MODEL, log=print) -> list[dict]:
    """저장된 묶음이 실행 기록보다 새로우면 그대로, 아니면 새로 만들어 저장. 임베딩이 실패하면 단어 기반으로"""
    path = bundles_path(manifest)
    if path.is_file() and path.stat().st_mtime >= Path(manifest).stat().st_mtime:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        bundles = build_bundles(manifest, make_similarity("embedding" if client else "lexical", manifest, client,
                                                          embed_model))
    except Exception as exc:  # 임베딩 API 실패 등
        log(f"[judge_context] embedding retrieval failed ({type(exc).__name__}: {exc}); using lexical similarity")
        bundles = build_bundles(manifest)
    path.write_text(json.dumps(bundles, ensure_ascii=False, indent=1), encoding="utf-8")
    return bundles


# ---------------------------------------------------------------- 사람 채점 (판단 시점 단위)
# <manifest>.anchor_ratings.<채점자>.json: 판단 시점(에이전트, step)마다 0~10점과 메모.
# 같은 시점의 판정기 점수(judges.json의 '<모델>@anchor')와 judge_agreement로 비교

ANCHOR_RUBRIC = ("평가 기준 (0~10): 이 시점에 에이전트가 바깥 맥락(바뀐 상황, 상대의 말과 필요, 앞서 알게 된 사실과 실패)을 "
                 "고려해 반응했는가. 실제 코드와 행동으로 이어지지 않은 계획이나 긴 주석에는 점수를 주지 마세요.")


def anchor_ratings_path(manifest, rater: str) -> Path:
    manifest = Path(manifest)
    safe = re.sub(r"[^\w.-]+", "-", rater.strip()).strip("-")
    if not safe:
        raise ValueError("채점자 이름을 입력하세요.")
    return manifest.with_name(f"{manifest.stem}.anchor_ratings.{safe}.json")


def load_anchor_ratings(manifest, rater: str) -> dict[str, dict]:
    path = anchor_ratings_path(manifest, rater)
    if not path.is_file():
        return {}
    return {judge_agreement.turn_key(r["step"], r["agent"]): r
            for r in json.loads(path.read_text(encoding="utf-8")).get("ratings", [])}


def load_all_anchor_ratings(manifest) -> dict[str, dict[str, float]]:
    """채점자 이름 -> {turn_key: 점수}"""
    manifest = Path(manifest)
    prefix = manifest.stem + ".anchor_ratings."
    result = {}
    for path in manifest.parent.glob(prefix + "*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        result[data.get("rater") or path.name[len(prefix):-5]] = {
            judge_agreement.turn_key(r["step"], r["agent"]): r["score"] for r in data.get("ratings", [])}
    return result


def save_anchor_rating(manifest, rater: str, bundle: dict, score, comment: str = "") -> None:
    """score=None이면 그 시점의 채점을 지움."""
    if score is not None and not (isinstance(score, (int, float)) and 0 <= score <= 10):
        raise ValueError("점수는 0~10이어야 합니다.")
    ratings = load_anchor_ratings(manifest, rater)
    key = judge_agreement.turn_key(bundle["step"], bundle["agent"])
    ratings.pop(key, None)
    if score is not None:
        ratings[key] = {"step": bundle["step"], "agent": bundle["agent"], "score": score, "comment": comment.strip(),
                        "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    ordered = sorted(ratings.values(), key=lambda r: (r["step"], str(r["agent"])))
    anchor_ratings_path(manifest, rater).write_text(json.dumps(
        {"rater": rater.strip(), "manifest": Path(manifest).name, "rubric": ANCHOR_RUBRIC, "ratings": ordered},
        ensure_ascii=False, indent=2), encoding="utf-8")


def judge_scores(manifest) -> dict[str, dict[str, float]]:
    """판정 모델('@anchor' 뗀 이름) -> {turn_key: 점수}"""
    return {name[:-len(judge_agreement.ANCHOR_SUFFIX)]: scores
            for name, scores in judge_agreement.load_judges(manifest, "anchor").items()}


def summary(manifest, bundles: list[dict], rater: str) -> str:
    judges, mine = judge_scores(manifest), load_anchor_ratings(manifest, rater) if rater.strip() else {}
    parts = [f"판단 시점 {len(bundles)}개"]
    for name, scores in judges.items():
        values = list(scores.values())
        parts.append(f"{name.split('/')[-1]} 평균 {sum(values) / len(values):.1f}" if values else name)
    if mine:
        human = {k: r["score"] for k, r in mine.items()}
        parts.append(f"내 채점 {len(human)}/{len(bundles)} 평균 {sum(human.values()) / len(human):.1f}")
        for name, scores in judges.items():
            agree = judge_agreement.compare(scores, human)
            if agree["n"] >= 2:
                parts.append(f"vs {name.split('/')[-1]}: r={agree['pearson']} MAE={agree['mae']} (n={agree['n']})")
    return "   ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Build judge decision-point bundles from a finished run.")
    parser.add_argument("manifest")
    parser.add_argument("--retrieval", choices=("embedding", "lexical"), default="embedding")
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--api-key-file", default="key.txt")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--max-anchors", type=int, default=12, help="per agent")
    parser.add_argument("--show", type=int, default=0, help="print the first N rendered bundles")
    args = parser.parse_args()
    client = None
    if args.retrieval == "embedding":
        from openai import OpenAI
        from maci_judge import read_secret
        client = OpenAI(base_url=args.base_url, api_key=read_secret(args.api_key_file))
    bundles = build_bundles(args.manifest, make_similarity(args.retrieval, args.manifest, client, args.embed_model),
                            top_k=args.top_k, max_anchors=args.max_anchors)
    bundles_path(args.manifest).write_text(json.dumps(bundles, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(bundles)} bundles -> {bundles_path(args.manifest)}")
    for bundle in bundles[:args.show]:
        print("\n" + render(bundle))


if __name__ == "__main__":
    main()
