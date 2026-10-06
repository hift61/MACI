# 무작위 맵 생성 패키지. 구성:
#   spec.py      - MapSpec: 맵 한 판의 순수 데이터 (JSON 저장/불러오기)
#   layout.py    - Layout: 벽 생성, 빈 좌표 뽑기
#   puzzles.py   - 퍼즐 템플릿 (PUZZLES에 등록)
#   generator.py - generate_map(seed, GenConfig) -> MapSpec
#   builder.py   - build_environment(MapSpec) -> Environment (enviroment/에 의존하는 유일한 파일)
#   hints.py     - auto_hints(MapSpec): 직접 만든 맵의 과제 설명 자동 생성
#   editor_model.py - EditorModel: 맵 편집 동작/검증/저장 (pygame 없이 동작)
#   editor.py    - pygame 맵 에디터 화면 (python -m mapgen.editor, pygame을 쓰는 유일한 파일)
#   __main__.py  - python -m mapgen 명령행 도구 (생성/미리보기/저장, --edit로 에디터 열기)
# builder는 Environment를 import하므로 여기서 자동으로 불러오지 않음 - 필요할 때
# `from mapgen.builder import build_environment`로 따로 import
from .generator import GenConfig, generate_map
from .spec import MapSpec

__all__ = ["GenConfig", "MapSpec", "generate_map"]
