"""MACI judge: scores a completed benchmark.py run's manifest.jsonl.

Ported from the sibling MACI benchmark project's maci_judge.py: a judge
model reads each turn's state and rates it 0-10, per-turn scores are
averaged into a raw 0-10 index, then linearly scaled to a 0-5000 benchmark
score calibrated so a reference model (--baseline-model, default
upstage/solar-pro4) defines 100 points - run once on a reference-model
manifest with --set-baseline before scoring other runs.

The one real adaptation from the source implementation: there, the judge is
shown the acting model's chain-of-thought text. A Code-as-Policies agent
(see enviroment/policy.py) has no CoT to show - its "reasoning" IS the
decide() code it wrote - so here the judge is shown that code plus the
action it produced instead, and judges (1) whether the code's logic is
sound given what the agent could perceive, and (2) whether the resulting
action makes real progress (including coordinating with the other agent
when the task needs it).

Usage:
    python maci_judge.py path/to/manifest.jsonl --set-baseline
    python maci_judge.py path/to/other_manifest.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time

from openai import APIConnectionError, APIStatusError, OpenAI

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE_FILE = os.path.join(HERE, "maci_judge_baseline.json")

MAX_SCORE = 5000
BASELINE_TARGET = 100
DEFAULT_BASELINE_MODEL = "upstage/solar-pro4"
DEFAULT_JUDGE_MODEL = "nvidia/nemotron-3.5-lightning"

JUDGE_PARAMS = dict(temperature=0.0, top_p=1.0, seed=0)
DEFAULT_TOKEN_BUDGET = 2000

CONTEXT_OVERFLOW_MARKERS = ("exceed_context_size_error", "context size", "exceeds the available context")

SYSTEM_PROMPT = (
    "You are an expert judge evaluating one turn of a cooperative multi-agent "
    "system in which each agent is driven by Python policy code an LLM wrote "
    "for itself (Code as Policies). You will be shown the agent's task, its "
    "current policy code, the action that code produced this turn (both what "
    "the policy chose and what actually executed, if a rule overrode it), and "
    "recent messages. Judge two things together as a single combined score: "
    "(1) soundness - does the code's logic make sense given the task and what "
    "the agent could actually perceive (no assumptions about information it "
    "couldn't have); (2) progress - does the resulting action move the agents "
    "toward completing the shared task, including real coordination with the "
    "other agent when the task requires it. "
    "Reply with only a single number from 0 to 10."
)


def read_secret(filename: str = "key.txt") -> str:
    """Read the API key from a file relative to this project's directory."""
    filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    try:
        with open(filename, encoding="utf-8-sig") as f:
            value = f.read().strip()
    except FileNotFoundError:
        raise SystemExit(
            f"Missing credential: create {filename} containing just the API key."
        )
    if not value:
        raise SystemExit(f"Empty credential file: put your API key in {filename}.")
    return value


def with_retry(fn, *args, retries=3, delay=2.0, **kwargs):
    """Retry on transient network/5xx/429 errors. 4xx errors other than 429
    (e.g. a too-long prompt) are deterministic - retrying the identical
    request just fails the same way again, so those are raised immediately
    instead of wasting the retry budget."""
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except APIStatusError as e:
            status = getattr(e, "status_code", None)
            if status is not None and status < 500 and status != 429:
                raise
            if attempt == retries - 1:
                raise
            time.sleep(delay * (attempt + 1))
        except APIConnectionError:
            if attempt == retries - 1:
                raise
            time.sleep(delay * (attempt + 1))


def is_context_overflow_error(exc) -> bool:
    if not isinstance(exc, APIStatusError):
        return False
    if getattr(exc, "status_code", None) not in (400, 413):
        return False
    return any(marker in str(exc).lower() for marker in CONTEXT_OVERFLOW_MARKERS)


def extract_reasoning_delta(delta) -> str:
    """Pulls whatever reasoning text a streamed delta carries, in whichever
    shape the judge model/provider uses: a plain `reasoning` string, or
    `reasoning_details` - a list of blocks each carrying a "text" field."""
    piece = getattr(delta, "reasoning", None)
    if piece:
        return piece
    details = getattr(delta, "reasoning_details", None) or []
    parts = []
    for item in details:
        text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def build_turn_summary(record: dict, agent_record: dict) -> str:
    """Simplifies one manifest.jsonl line down to what matters for judging
    one agent's turn - mirrors the source implementation's map-state
    simplification, adapted to MACI's own object/observation shape."""
    lines = [f"Step {record.get('step')}"]
    lines.append(f"Task for this agent: {(record.get('task') or {}).get(agent_record.get('agent'), '')}")
    lines.append(f"Position: {agent_record.get('position')}")
    lines.append(f"Objectives: {record.get('objectives')}  (all achieved so far: {record.get('cleared')})")

    decision = agent_record.get("decision") or {}
    lines.append(f"Policy chose: {decision.get('action')}")
    lines.append(f"Actually executed (after rules): {decision.get('final_action')} (overridden={decision.get('overridden')})")
    if decision.get("replan"):
        lines.append(f"Policy code was regenerated this turn because it got stuck: {decision['replan'].get('reason')}")
    if decision.get("policy_error"):
        lines.append(f"Policy error this turn (fell back to noop): {decision.get('policy_error')}")

    messages = (record.get("messages") or [])[-5:]
    if messages:
        lines.append("Messages delivered this step:")
        for m in messages:
            lines.append(f"  -> {m.get('receiver_id')}: {json.dumps(m, ensure_ascii=False)}")
    return "\n".join(lines)


def _build_user_prompt(turn_summary: str, code: str) -> str:
    return (
        f"=== TURN STATE ===\n{turn_summary}\n\n"
        f"=== AGENT'S CURRENT POLICY CODE ===\n{code or '(none captured for this turn)'}\n\n"
        f"Score (0-10):"
    )


def judge_turn(client, judge_model: str, record: dict, agent_record: dict, log=None) -> float:
    """Streams one judge call for a single agent turn. Grows the token
    budget (up to 4x) and retries if the judge model is cut off
    mid-reasoning, returns NaN instead of guessing if it still doesn't fit,
    and reacts to (rather than pre-guesses) context overflow by shrinking
    the policy code text first."""
    if log is None:
        def log(msg):
            print(msg, flush=True)

    full_code = agent_record.get("generated_code") or ""
    turn_summary = build_turn_summary(record, agent_record)

    code_budget = None  # None = send the full code; only shrink once the server rejects it
    token_budget = DEFAULT_TOKEN_BUDGET
    max_token_budget = token_budget * 4

    while True:
        code_text = full_code
        if code_budget is not None and len(code_text) > code_budget:
            code_text = "...(earlier code trimmed)...\n" + code_text[-code_budget:]
        user_prompt = _build_user_prompt(turn_summary, code_text)

        try:
            stream = with_retry(
                client.chat.completions.create,
                model=judge_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                extra_body={"reasoning": {"enabled": True}},
                stream=True,
                max_tokens=token_budget,
                **JUDGE_PARAMS,
            )
            content_chunks, reasoning_chunks = [], []
            finish_reason = None
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                reasoning_piece = extract_reasoning_delta(delta)
                if reasoning_piece:
                    reasoning_chunks.append(reasoning_piece)
                if delta.content:
                    content_chunks.append(delta.content)
            text = "".join(content_chunks).strip()
            judge_reasoning_text = "".join(reasoning_chunks).strip()

            unclosed_inline_think = "<think>" in text and "</think>" not in text
            no_answer_yet = bool(judge_reasoning_text) and not re.sub(r"(?is)<think>.*?</think>", "", text).strip()
            truncated = finish_reason == "length" and (unclosed_inline_think or no_answer_yet)
            if truncated and token_budget < max_token_budget:
                token_budget = min(token_budget * 2, max_token_budget)
                log(f"[maci_judge] judge cut off mid-reasoning; retrying with max_tokens={token_budget}")
                continue
            break
        except APIStatusError as e:
            if not is_context_overflow_error(e):
                raise
            next_budget = (code_budget // 2) if code_budget is not None else (len(full_code) // 2)
            if next_budget < 200:
                log("[maci_judge] WARNING: prompt too long even after trimming code; scoring as NaN.")
                return float("nan")
            code_budget = next_budget
            log(f"[maci_judge] judge prompt too long; trimming code to last {code_budget} chars and retrying...")
            continue
        except Exception as e:
            # with_retry only guards the initial request; a dropped connection
            # mid-stream surfaces here instead, while iterating the response.
            log(f"[maci_judge] WARNING: judge stream failed ({type(e).__name__}: {e}); returning NaN for this turn.")
            return float("nan")

    answer_only = re.sub(r"(?is)<think>.*?</think>", "", text).strip()
    if ("<think>" in text and "</think>" not in text) or (not answer_only and judge_reasoning_text):
        log(f"[maci_judge] WARNING: judge reasoning still truncated after retries (finish_reason={finish_reason!r}); returning NaN.")
        return float("nan")

    # "7/10", "6 out of 10"의 분모 10을 점수로 읽지 않도록 먼저 제거
    answer = re.sub(r"(?i)\s*(?:/|out of)\s*10(?:\.0+)?\b", "", answer_only or text)
    numbers = re.findall(r"-?\d+(?:\.\d+)?", answer)
    if not numbers:
        return float("nan")
    return max(0.0, min(10.0, float(numbers[-1])))


def score_run(manifest_path, client, judge_model, agent_filter=None, max_turns=None, log=None):
    if log is None:
        def log(msg):
            print(msg, flush=True)
    scores = []
    per_turn = []
    actor_models = set()

    with open(manifest_path, "r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    if max_turns:
        lines = lines[:max_turns]

    for line in lines:
        record = json.loads(line)
        for agent_record in record.get("agents", []):
            label = agent_record.get("agent")
            if agent_filter and label != agent_filter:
                continue
            actor_models.add(agent_record.get("model", ""))
            score = judge_turn(client, judge_model, record, agent_record, log=log)
            log(f"[maci_judge] step={record.get('step')} agent={label} score={score}")
            per_turn.append({"step": record.get("step"), "agent": label, "score": score})
            if score == score:  # skip NaN
                scores.append(score)

    raw_avg = sum(scores) / len(scores) if scores else float("nan")
    return {
        "raw_avg": raw_avg,
        "n_scored": len(scores),
        "n_total": len(per_turn),
        "per_turn": per_turn,
        "actor_models": sorted(m for m in actor_models if m),
    }


def load_baselines() -> dict:
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_baseline(model_name: str, raw_avg: float) -> None:
    baselines = load_baselines()
    baselines[model_name] = raw_avg
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(baselines, f, ensure_ascii=False, indent=2)


def scale_score(raw_avg: float, baseline_model: str):
    """Returns (scaled_score, baseline_raw) if a baseline has been recorded
    for baseline_model, else (None, None). Calibration is
    (raw_avg / baseline_raw) * BASELINE_TARGET, capped at MAX_SCORE - so the
    baseline run itself always scores exactly BASELINE_TARGET, and
    better/worse runs scale proportionally around it."""
    baseline_raw = load_baselines().get(baseline_model)
    if not baseline_raw:
        return None, None
    scaled = (raw_avg / baseline_raw) * BASELINE_TARGET
    return min(MAX_SCORE, scaled), baseline_raw


def main():
    parser = argparse.ArgumentParser(description="Score a completed MACI benchmark.py run's manifest.jsonl with a judge model.")
    parser.add_argument("manifest", help="path to manifest.jsonl")
    parser.add_argument("--agent", default=None, help="only judge this agent label (e.g. A); default: all agents")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-file", default="key.txt", help="API key file (relative paths use the project directory)")
    parser.add_argument("--max-turns", type=int, default=None, help="limit how many manifest lines to judge (for a quick check)")
    parser.add_argument("--baseline-model", default=DEFAULT_BASELINE_MODEL)
    parser.add_argument("--set-baseline", action="store_true", help="register this run's average as the --baseline-model's 100-point baseline")
    parser.add_argument("--force-baseline", action="store_true", help="allow --set-baseline even if the manifest's actor model doesn't look like --baseline-model")
    args = parser.parse_args()

    api_key = read_secret(args.api_key_file)
    client = OpenAI(base_url=args.base_url, api_key=api_key)
    result = score_run(args.manifest, client, args.judge_model, agent_filter=args.agent, max_turns=args.max_turns)

    print(f"\nActor model(s) in this run: {result['actor_models']}")
    print(f"Raw average judge score: {result['raw_avg']:.3f} / 10 over {result['n_scored']}/{result['n_total']} scored turns")

    if args.set_baseline:
        actor_matches = any(args.baseline_model in m for m in result["actor_models"])
        if result["raw_avg"] != result["raw_avg"]:  # NaN: 채점된 턴이 하나도 없음
            print("[REFUSED] --set-baseline: no turn was scored (all NaN), so there is no baseline to save.")
        elif not actor_matches and not args.force_baseline:
            print(
                f"[REFUSED] --set-baseline expects a manifest actually run with {args.baseline_model}, "
                f"but this manifest's actor model(s) were {result['actor_models']}. "
                f"Re-run with a {args.baseline_model} manifest, or pass --force-baseline if this is intentional."
            )
        else:
            save_baseline(args.baseline_model, result["raw_avg"])
            print(f"Saved baseline for {args.baseline_model}: raw {result['raw_avg']:.3f} -> now defines {BASELINE_TARGET} points")

    scaled, baseline_raw = scale_score(result["raw_avg"], args.baseline_model)
    if scaled is None:
        fallback = (result["raw_avg"] / 10) * MAX_SCORE if result["raw_avg"] == result["raw_avg"] else float("nan")
        print(f"[WARNING] No {args.baseline_model} baseline recorded yet - run this judge on a {args.baseline_model} manifest with --set-baseline first.")
        print(f"Uncalibrated fallback score (linear 0-10 -> 0-{MAX_SCORE}): {fallback:.1f} / {MAX_SCORE}")
    else:
        print(f"Benchmark score: {scaled:.1f} / {MAX_SCORE}  (baseline raw={baseline_raw:.3f} => {args.baseline_model} = {BASELINE_TARGET})")


if __name__ == "__main__":
    main()
