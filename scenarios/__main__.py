"""python -m scenarios            모든 시나리오를 map_datas/<이름>.json으로 내보냄 (런처 맵 목록에 바로 나타남)
python -m scenarios --check    내보내기 전에 정답/실수 스크립트로 모두 풀리는지 검증
python -m scenarios --list     시나리오 목록만 출력
python -m scenarios s05_lossy_sync s06_short_radio   일부만 내보내기
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scenarios import SCENARIO_NAMES, load  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="내보낼 시나리오 (생략하면 전부)")
    parser.add_argument("--out-dir", default=os.path.join(ROOT, "map_datas"))
    parser.add_argument("--check", action="store_true", help="정답/실수 스크립트로 풀리는지 먼저 검증")
    parser.add_argument("--list", action="store_true")
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

    if args.check:
        from scenarios.oracle import run
        failed = []
        for name in names:
            for mode in ("solution", "mistake"):
                step, _ = run(load(name), mode)
                print(f"{name:24s} {mode:8s} " + (f"cleared at step {step}" if step else "NOT CLEARED"))
                if step is None:
                    failed.append((name, mode))
        if failed:
            raise SystemExit(f"check failed: {failed}")

    os.makedirs(args.out_dir, exist_ok=True)
    for name in names:
        path = os.path.join(args.out_dir, f"{name}.json")
        load(name).build().save(path)
        print(f"wrote {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
