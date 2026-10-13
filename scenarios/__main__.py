"""python -m scenarios            모든 시나리오를 map_datas/<이름>.json(단서에 규칙 힌트 있음)과
                               map_datas/<이름>_nohint.json(단서에 퍼즐 자료만)으로 내보냄 (런처 맵 목록에 바로 나타남)
python -m scenarios --check    내보내기 전에 정답/실수 스크립트로 모두 풀리는지 검증
python -m scenarios --list     시나리오 목록만 출력
python -m scenarios --texts    에이전트가 읽는 글(목표, 단계 안내, 단서, 화면)을 scenarios/AGENT_TEXTS.md로 생성
python -m scenarios s05_lossy_sync s06_short_radio   일부만 내보내기
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scenarios import SCENARIO_NAMES, load  # noqa: E402
from scenarios.common import NOHINT_SUFFIX, without_clue_hints  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="내보낼 시나리오 (생략하면 전부)")
    parser.add_argument("--out-dir", default=os.path.join(ROOT, "map_datas"))
    parser.add_argument("--check", action="store_true", help="정답/실수 스크립트로 풀리는지 먼저 검증")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--texts", action="store_true", help="에이전트가 읽는 글을 scenarios/AGENT_TEXTS.md로 생성")
    args = parser.parse_args()

    names = args.names or SCENARIO_NAMES
    unknown = [n for n in names if n not in SCENARIO_NAMES]
    if unknown:
        parser.error(f"unknown scenario(s): {unknown}. choose from {SCENARIO_NAMES}")
    if args.list:
        for name in names:
            module = load(name)
            print(f"{name:24s} {module.FAMILY:8s} {module.TITLE}")
        return

    if args.texts:
        path = os.path.join(ROOT, "scenarios", "AGENT_TEXTS.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(agent_texts(names))
        print(f"wrote {os.path.relpath(path, ROOT)}")
        return

    if args.check:
        from scenarios.oracle import run
        failed = []
        for name in names:
            for hints in (True, False):
                label = name if hints else name + NOHINT_SUFFIX
                for mode in ("solution", "mistake"):
                    step, _ = run(load(name), mode, clue_hints=hints)
                    print(f"{label:31s} {mode:8s} " + (f"cleared at step {step}" if step else "NOT CLEARED"))
                    if step is None:
                        failed.append((label, mode))
        if failed:
            raise SystemExit(f"check failed: {failed}")

    os.makedirs(args.out_dir, exist_ok=True)
    for name in names:
        spec = load(name).build()
        for out_name, out_spec in ((name, spec), (name + NOHINT_SUFFIX, without_clue_hints(spec))):
            path = os.path.join(args.out_dir, f"{out_name}.json")
            out_spec.save(path)
            print(f"wrote {os.path.relpath(path, ROOT)}")


# 맵마다 에이전트가 읽게 되는 글을 그대로 모은 문서 (사람 검토용). 공통 설명/시스템 프롬프트는 제외
def agent_texts(names) -> str:
    import json
    from mapgen.builder import build_environment
    from scenarios.common import _strip_clue_hints

    def show(value):
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    def text_objects(objects):
        kept = {o["id"]: o["params"].get("content") for o in _strip_clue_hints(objects)}
        rows = []
        for o in objects:
            kind, params = o["kind"], o["params"]
            if kind in ("clue", "variant_clue", "display"):
                nohint = show(kept[o["id"]]) if o["id"] in kept else "(없음)"
                if kind == "display" or o["id"] in kept and kept[o["id"]] == params.get("content"):
                    nohint = "(같음)"
                rows.append(f"| `{o['id']}` | {kind}{' (가까이 가야 보임)' if params.get('hidden') else ''} | "
                            f"{show(params.get('content'))} | {nohint} |")
                for agent_id, content in (params.get("variants") or {}).items():
                    rows.append(f"| `{o['id']}` | {agent_id}에게 보이는 내용 | {show(content)} | (같음) |")
            elif params.get("label"):
                rows.append(f"| `{o['id']}` | {kind} 이름표 | {params['label']} | (같음) |")
        return rows

    lines = ["# 에이전트가 읽는 글 (자동 생성: python -m scenarios --texts)", "",
             "맵마다 에이전트에게 전달되는 글입니다. 모든 맵에 같은 공통 설명(시야, 이동, 메시지, 토큰, 감점)과 "
             "시스템 프롬프트의 물체 역할 설명은 빼고, 맵마다 다른 부분만 모았습니다. 원칙은 "
             "`scenarios/common.py`의 make_spec 주석과 MAP_HOWTO.md 6장을 따릅니다. 마지막 열은 같은 맵의 힌트 없는 "
             "버전(map_datas/<이름>_nohint.json)에서 그 단서가 어떻게 보이는지입니다(규칙 문장을 지우고 퍼즐 자료만 남김, "
             "남는 것이 없으면 단서 자체가 없음).", ""]
    for name in names:
        spec = load(name).build()
        _, tasks, _ = build_environment(spec)
        task = tasks[spec.agents[0]["id"]]
        goal = task[task.index("Goal: "):] if "Goal: " in task else "(목표 숨김)"
        lines += [f"## {name} ({load(name).TITLE})", "", f"- **과제 설명의 맵별 부분**: {goal.replace(chr(10), ' / ')}"]
        if spec.rules:
            rules = {k: v for k, v in spec.rules.items() if k not in ("stages", "glass_walls")}
            if rules:
                lines.append(f"- **맵 규칙**: `{json.dumps(rules, ensure_ascii=False)}`")
        rows = text_objects(spec.objects)
        if rows:
            lines += ["", "| 물체 | 종류 | 내용 | _nohint 버전 |", "|---|---|---|---|"] + rows
        for i, st in enumerate((spec.rules or {}).get("stages", []), 1):
            lines += ["", f"**{i}단계 '{st['title']}'** - 단계 안내: {st['briefing']}"]
            rows = text_objects(st["objects"])
            if rows:
                lines += ["", "| 물체 | 종류 | 내용 | _nohint 버전 |", "|---|---|---|---|"] + rows
        lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
