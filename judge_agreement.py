"""판정 모델끼리, 그리고 판정 모델과 사람 채점이 같은 턴을 얼마나 비슷하게 채점했는지 계산.

판정 결과: <manifest 이름>.judges.json  (maci_judge.py가 판정 모델별로 저장)
사람 채점: <manifest 이름>.human.<채점자>.json  (launcher.py의 '사람 채점' 탭이 저장)
둘 다 (step, agent) 턴마다 0~10점이며, 양쪽이 모두 채점한 턴만 비교한다.

지표: n(공통 턴 수), Pearson r, Spearman ρ, MAE(평균 절대 차이), within_1(1점 이내 일치 비율),
QWK(quadratic weighted kappa, 정수로 반올림한 0~10 등급의 우연 보정 일치도).
사람이 여러 명이면 '사람 평균', 판정 모델이 여러 개면 '판정 평균'도 함께 비교한다.

Usage:
    python judge_agreement.py benchmark_runs/run.jsonl
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import re
from pathlib import Path

HUMAN_MEAN = "사람 평균"
JUDGE_MEAN = "판정 평균"


def turn_key(step, agent) -> str:
    return f"{step}|{agent}"


def judge_path(manifest) -> Path:
    manifest = Path(manifest)
    return manifest.with_name(manifest.stem + ".judges.json")


def human_path(manifest, rater: str) -> Path:
    manifest = Path(manifest)
    safe = re.sub(r"[^\w.-]+", "-", rater.strip()).strip("-")
    if not safe:
        raise ValueError("채점자 이름을 입력하세요.")
    return manifest.with_name(f"{manifest.stem}.human.{safe}.json")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


ANCHOR_SUFFIX = "@anchor"  # maci_judge --unit anchor 결과 (판단 시점 단위). step 단위 결과와 섞어 비교하지 않음


def load_judges(manifest, unit: str = "step") -> dict[str, dict[str, float]]:
    return {model: {turn_key(t["step"], t["agent"]): t["score"] for t in data.get("per_turn", [])
                    if t.get("score") is not None}
            for model, data in _read(judge_path(manifest)).items()
            if model.endswith(ANCHOR_SUFFIX) == (unit == "anchor")}


def save_judge_result(manifest, judge_model: str, result: dict) -> None:
    path = judge_path(manifest)
    data = _read(path)
    data[judge_model] = {**result, "per_turn": [
        {**turn, "score": turn["score"] if turn["score"] == turn["score"] else None}  # NaN -> null
        for turn in result["per_turn"]]}
    if data[judge_model].get("raw_avg") != data[judge_model].get("raw_avg"):
        data[judge_model]["raw_avg"] = None
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_humans(manifest) -> dict[str, dict[str, float]]:
    manifest = Path(manifest)
    humans = {}
    for path in sorted(manifest.parent.glob(manifest.stem + ".human.*.json")):
        data = _read(path)
        humans[data.get("rater") or path.stem.split(".human.", 1)[1]] = {
            turn_key(s["step"], s["agent"]): s["score"] for s in data.get("scores", [])}
    return humans


def save_human_score(manifest, rater: str, step, agent: str, score) -> None:
    """score=None removes this rater's score for the turn."""
    if score is not None and not (isinstance(score, (int, float)) and 0 <= score <= 10):
        raise ValueError("점수는 0~10이어야 합니다.")
    path = human_path(manifest, rater)
    data = _read(path) or {"rater": rater.strip(), "manifest": Path(manifest).name, "scores": []}
    scores = [s for s in data["scores"] if turn_key(s["step"], s["agent"]) != turn_key(step, agent)]
    if score is not None:
        scores.append({"step": step, "agent": agent, "score": score,
                       "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds")})
    data["scores"] = sorted(scores, key=lambda s: (s["step"], str(s["agent"])))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None  # 한쪽 점수가 모두 같으면 상관계수가 정의되지 않음
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1  # 동점은 평균 순위
        i = j + 1
    return ranks


def _quadratic_weighted_kappa(xs, ys, low=0, high=10):
    a = [min(high, max(low, round(x))) - low for x in xs]
    b = [min(high, max(low, round(y))) - low for y in ys]
    k, n = high - low + 1, len(a)
    observed = [[0] * k for _ in range(k)]
    for i, j in zip(a, b):
        observed[i][j] += 1
    hist_a = [a.count(i) for i in range(k)]
    hist_b = [b.count(i) for i in range(k)]
    numerator = denominator = 0.0
    for i in range(k):
        for j in range(k):
            weight = (i - j) ** 2 / (k - 1) ** 2
            numerator += weight * observed[i][j]
            denominator += weight * hist_a[i] * hist_b[j] / n
    return None if denominator == 0 else 1 - numerator / denominator


def compare(a: dict[str, float], b: dict[str, float]) -> dict:
    common = sorted(set(a) & set(b))
    result = {"n": len(common), "pearson": None, "spearman": None, "mae": None, "within_1": None, "qwk": None}
    if not common:
        return result
    xs, ys = [a[k] for k in common], [b[k] for k in common]
    result["mae"] = sum(abs(x - y) for x, y in zip(xs, ys)) / len(common)
    result["within_1"] = sum(abs(x - y) <= 1 for x, y in zip(xs, ys)) / len(common)
    if len(common) >= 2:
        result["pearson"] = _pearson(xs, ys)
        result["spearman"] = _pearson(_ranks(xs), _ranks(ys))
        result["qwk"] = _quadratic_weighted_kappa(xs, ys)
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in result.items()}


def _mean_scores(raters: dict[str, dict[str, float]]) -> dict[str, float]:
    totals: dict[str, list[float]] = {}
    for scores in raters.values():
        for key, value in scores.items():
            totals.setdefault(key, []).append(value)
    return {key: sum(values) / len(values) for key, values in totals.items()}


def report(manifest, unit: str = "step", humans: dict | None = None) -> dict:
    """unit="anchor"면 판단 시점 판정끼리, humans로 받은 사람 점수(판단 시점 채점)와 비교"""
    judges = load_judges(manifest, unit)
    humans = load_humans(manifest) if humans is None else humans
    sources = {f"판정:{name}": scores for name, scores in judges.items()}
    sources.update({f"사람:{name}": scores for name, scores in humans.items()})
    if len(humans) > 1:
        sources[HUMAN_MEAN] = _mean_scores(humans)
    if len(judges) > 1:
        sources[JUDGE_MEAN] = _mean_scores(judges)
    names = list(sources)
    pairs = []
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            # 평균은 그 평균을 만든 개별 점수와 비교하지 않음
            pair = {first, second}
            if (HUMAN_MEAN in pair and any(n.startswith("사람:") for n in pair)) or \
                    (JUDGE_MEAN in pair and any(n.startswith("판정:") for n in pair)):
                continue
            pairs.append({"a": first, "b": second, **compare(sources[first], sources[second])})
    return {"manifest": str(manifest), "judges": sorted(judges), "humans": sorted(humans),
            "turns_scored": {name: len(scores) for name, scores in sources.items()}, "pairs": pairs}


def format_report(result: dict) -> list[str]:
    lines = [f"판정 모델: {', '.join(result['judges']) or '없음'}  /  사람 채점자: {', '.join(result['humans']) or '없음'}"]
    if not result["pairs"]:
        lines.append("비교할 채점 결과가 두 개 이상 필요합니다.")
    for pair in result["pairs"]:
        fmt = lambda v: "-" if v is None else f"{v:.3f}"
        lines.append(f"{pair['a']}  vs  {pair['b']}:  공통 {pair['n']}턴  r={fmt(pair['pearson'])}  "
                     f"ρ={fmt(pair['spearman'])}  QWK={fmt(pair['qwk'])}  MAE={fmt(pair['mae'])}  "
                     f"1점 이내={fmt(pair['within_1'])}")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest")
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    args = parser.parse_args()
    result = report(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else "\n".join(format_report(result)))


if __name__ == "__main__":
    main()
