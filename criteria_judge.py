"""항목별 판정: 판단 시점(judge_context 묶음)마다 다섯 항목(judge_context.CRITERIA, rande-rubric-1.0-proposed) 각각을
OpenRouter decisions 모델로 판정하고, 여러 모델이 확실히 일치한 판정만 받아들임.

    python criteria_judge.py benchmark_runs/x/s01_deadlock.jsonl
    python criteria_judge.py run.jsonl --judge-model cloudflare/clef-flash,typesafe/jev-1.14 --threshold 0.8

- 판정 단위: 판단 시점 x 항목. 모델마다 한 번 호출에 항목별 두 문항을 함께 물음
    평가 기회: present / absent  (absent = 평가 기회 없음)
    판정:     yes(충족) / no(미충족) / unknown(근거 부족)
- 판정 수락 (항목 하나): 모든 모델이 같은 답을 고르고 그 답의 평균 확률이 --threshold(0.8) 이상
    1) 평가 기회가 present로 확정되어야 판정을 봄. absent로 확정되면 '평가 기회 없음', 그 밖은 '보류'
    2) 판정이 yes/no로 확정되면 수락, unknown으로 확정되면 '근거 부족', 그 밖(불일치, 확률 부족)은 '보류'
- 점수: 수락된 판정 중 충족 비율 = yes / (yes + no). 항목별, 에이전트별, 전체. 수락된 판정이 없으면 null
- 결과: <manifest 이름>.criteria_judgments.json (모델별 원 답과 확률, 판정 상태, 요약). 다시 실행하면 이미 받은
  답은 다시 묻지 않음
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import judge_context
import providers

DEFAULT_JUDGES = "cloudflare/clef-flash,typesafe/jev-1.14"
THRESHOLD = 0.8
RETRIES = 5
OPPORTUNITY = ("present", "absent")
LABELS = ("yes", "no", "unknown")


def decisions_url(base_url: str) -> str:
    """OpenRouter decisions endpoint next to the chat API: .../api/v1 -> .../api/alpha/decisions"""
    root = base_url.rstrip("/")
    return (root[:-3] if root.endswith("/v1") else root) + "/alpha/decisions"


def questions() -> dict:
    result = {}
    for key, c in judge_context.CRITERIA.items():
        head = f"Criterion: {c['name']} ({key}). "
        result[f"{key}__opportunity"] = {
            "type": "choice", "instructions": head + "Is there an evaluation opportunity for this criterion at this "
                                                     "decision point? " + judge_context.CRITERIA_NOTE,
            "criteria": {"present": c["opportunity"], "absent": judge_context.LABEL_GUIDE["not_applicable"]}}
        result[f"{key}__label"] = {
            "type": "choice", "instructions": head + "Assuming the evaluation opportunity exists, judge the agent "
                                                     "on this criterion. " + judge_context.CRITERIA_NOTE,
            "criteria": {"yes": c["yes"], "no": c["no"], "unknown": c["unknown"]}}
    return result


def ask(url: str, api_key: str, model: str, rendered: str, log=print) -> dict | None:
    """모델 하나, 판단 시점 하나 -> {criterion: {"opportunity": {choice, probabilities}, "label": {...}}, "_cost": x}.
    모든 문항에 확률이 와야 성공. 실패하면 RETRIES번 다시, 끝내 실패하면 None"""
    body = {"model": model, "state": {"decision_point": rendered}, "questions": questions()}
    for attempt in range(1, RETRIES + 1):
        try:
            request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                             headers={"Authorization": "Bearer " + api_key,
                                                      "Content-Type": "application/json"})
            response = json.load(urllib.request.urlopen(request, timeout=300))
            answers, result = response.get("answers") or {}, {}
            for key in judge_context.CRITERIA:
                entry = {}
                for part, options in (("opportunity", OPPORTUNITY), ("label", LABELS)):
                    answer = answers.get(f"{key}__{part}") or {}
                    probs = {k: float(v) for k, v in (answer.get("probabilities") or {}).items() if k in options}
                    if answer.get("choice") not in options or not probs:
                        raise ValueError(f"no usable answer for {key}__{part}")
                    entry[part] = {"choice": answer["choice"], "probabilities": probs}
                result[key] = entry
            result["_cost"] = (response.get("usage") or {}).get("cost", 0.0) or 0.0
            return result
        except urllib.error.HTTPError as exc:
            log(f"[criteria_judge] {model} HTTP {exc.code} (attempt {attempt}): {exc.read()[:200]!r}")
        except Exception as exc:
            log(f"[criteria_judge] {model} failed (attempt {attempt}): {type(exc).__name__}: {exc}")
        time.sleep(2 * attempt)
    return None


def _agreed(parts: list[dict], threshold: float):
    """모든 모델이 같은 답이고 그 답의 평균 확률이 threshold 이상이면 (답, 평균 확률), 아니면 (None, 이유)"""
    choices = {p["choice"] for p in parts}
    if len(choices) != 1:
        return None, "disagree"
    choice = choices.pop()
    mean = sum(p["probabilities"].get(choice, 0.0) for p in parts) / len(parts)
    return (choice, mean) if mean >= threshold else (None, "low_confidence")


def verdict(per_model: dict, models: list[str], criterion: str, threshold: float = THRESHOLD) -> dict:
    """항목 하나의 최종 판정. status: accepted(label yes/no) / unknown / not_applicable / held(reason)"""
    if any(not per_model.get(m) for m in models):
        return {"status": "held", "reason": "missing"}
    opportunity, info = _agreed([per_model[m][criterion]["opportunity"] for m in models], threshold)
    if opportunity is None:
        return {"status": "held", "reason": f"opportunity_{info}"}
    if opportunity == "absent":
        return {"status": "not_applicable", "p": round(info, 4)}
    label, info = _agreed([per_model[m][criterion]["label"] for m in models], threshold)
    if label is None:
        return {"status": "held", "reason": f"label_{info}"}
    if label == "unknown":
        return {"status": "unknown", "p": round(info, 4)}
    return {"status": "accepted", "label": label, "p": round(info, 4)}


def summarize(points: list[dict]) -> dict:
    def ratio(verdicts):
        yes = sum(v.get("label") == "yes" for v in verdicts)
        no = sum(v.get("label") == "no" for v in verdicts)
        return {"yes": yes, "no": no, "score": round(yes / (yes + no), 4) if yes + no else None}

    def counts(verdicts):
        out = {}
        for v in verdicts:
            name = v["status"] if v["status"] != "held" else "held:" + v["reason"]
            out[name] = out.get(name, 0) + 1
        return out

    every = [(p["agent"], c, v) for p in points for c, v in p["verdicts"].items()]
    return {
        "overall": {**ratio([v for _, _, v in every]), "status_counts": counts([v for _, _, v in every]),
                    "n_judgments": len(every)},
        "by_criterion": {c: ratio([v for _, k, v in every if k == c]) for c in judge_context.CRITERIA},
        "by_agent": {a: ratio([v for b, _, v in every if b == a]) for a in sorted({a for a, _, _ in every})},
    }


def judgments_path(manifest) -> Path:
    manifest = Path(manifest)
    return manifest.with_name(manifest.stem + ".criteria_judgments.json")


def judge_run(manifest, bundles: list[dict], models: list[str], url: str, api_key: str,
              threshold: float = THRESHOLD, log=print) -> dict:
    path = judgments_path(manifest)
    previous = {}
    if path.is_file():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved.get("criteria_version") == judge_context.CRITERIA_VERSION:
            previous = {(p["agent"], p["step"]): p.get("answers", {}) for p in saved.get("points", [])}
    points, cost = [], 0.0
    for bundle in bundles:
        answers = dict(previous.get((bundle["agent"], bundle["step"]), {}))
        rendered = judge_context.render(bundle)
        for model in models:
            if answers.get(model):
                continue
            answer = ask(url, api_key, model, rendered, log=log)
            if answer is not None:
                cost += answer.pop("_cost")
                answers[model] = answer
        point = {"agent": bundle["agent"], "step": bundle["step"], "answers": answers,
                 "verdicts": {c: verdict(answers, models, c, threshold) for c in judge_context.CRITERIA}}
        points.append(point)
        log(f"[criteria_judge] {bundle['agent']}@{bundle['step']}: " + ", ".join(
            f"{c}={v.get('label') or v['status'] if v['status'] != 'held' else 'held'}" for c, v in point["verdicts"].items()))
    result = {"manifest": Path(manifest).name, "criteria_version": judge_context.CRITERIA_VERSION,
              "judges": models, "threshold": threshold, "cost_this_call": cost,
              "points": points, "summary": summarize(points)}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="Criterion-by-criterion judging of a MACI run with OpenRouter "
                                                 "decisions models (unanimous, confident verdicts only).")
    parser.add_argument("manifest")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGES, help="decisions models, comma-separated")
    parser.add_argument("--threshold", type=float, default=THRESHOLD,
                        help="mean probability the agreed answer needs (default 0.8)")
    parser.add_argument("--retrieval", choices=("embedding", "lexical"), default="embedding")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--max-anchors", type=int, default=12, help="decision points per agent")
    providers.add_arguments(parser, embed=True)
    args = parser.parse_args()
    if args.provider != "openrouter":
        parser.error("decisions models are only on OpenRouter")
    from openai import OpenAI
    api_key = providers.read_key(args)
    client = OpenAI(base_url=providers.base_url(args), api_key=api_key)
    similarity = judge_context.make_similarity(args.retrieval, args.manifest, client, providers.embed_model(args))
    bundles = judge_context.build_bundles(args.manifest, similarity, top_k=args.top_k, max_anchors=args.max_anchors)
    judge_context.bundles_path(args.manifest).write_text(json.dumps(bundles, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
    models = [m.strip() for m in args.judge_model.split(",") if m.strip()]
    result = judge_run(args.manifest, bundles, models, decisions_url(providers.base_url(args)), api_key,
                       args.threshold)
    s = result["summary"]
    print(f"\n{len(bundles)} decision points x {len(judge_context.CRITERIA)} criteria, judges {models}, "
          f"threshold {args.threshold}")
    print(f"overall score (yes / accepted): {s['overall']['score']}  yes={s['overall']['yes']} no={s['overall']['no']}")
    print(f"status: {s['overall']['status_counts']}")
    for c, r in s["by_criterion"].items():
        print(f"  {c:24s} {r['score']}  (yes {r['yes']} / no {r['no']})")
    print(f"cost this call: ${result['cost_this_call']:.4f} -> {judgments_path(args.manifest)}")


if __name__ == "__main__":
    main()
