"""시나리오 맵 패키지 (협력 실험용 고난도 환경 12종).

구성
  engine.py   - ScenarioEnvironment: 시나리오 전용 물체/규칙 (기존 Environment 상속, 원본 수정 없음)
  common.py   - 맵 조립 도구 (벽, 물체, MapSpec 만들기, 물체 설명문)
  oracle.py   - 정답 검증용 스크립트 정책 (테스트 전용, LLM 무관)
  sNN_*.py    - 시나리오 하나당 파일 하나: build() -> MapSpec, solution(env)/mistake(env) -> 검증용 plan
  __main__.py - python -m scenarios : 모든 시나리오를 map_datas/sNN_*.json으로 내보냄 (--check: 검증)
  SCENARIOS.md - 시나리오별 목표/의도/단서·화면 내용/정답 흐름 설명서

시나리오 파일은 Environment를 import하지 않음(solution/mistake 안에서만 oracle을 불러옴) -
맵 데이터만 필요하면 build()만 쓰면 됨.
"""
import importlib

SCENARIO_NAMES = [
    "s01_deadlock",
    "s02_leapfrog",
    "s03_split_experiment",
    "s04_half_mastermind",
    "s05_lossy_sync",
    "s06_short_radio",
    "s07_me_vs_us",
    "s08_boring_role",
    "s09_shared_budget",
    "s10_moving_world",
    "s11_pincer",
    "s12_unreliable_eyes",
    # 아래는 MAP_GUIDE.md(ARC-AGI-3 기조 + 실패 맵 분석)로 만든 맵
    "s13_crossed_testimony",
    "s14_silent_porters",
    "s15_glass_division",
]


def load(name: str):
    return importlib.import_module(f"{__name__}.{name}")


def all_scenarios() -> list:
    return [load(name) for name in SCENARIO_NAMES]
