import json
from dataclasses import asdict, dataclass, field

# 생성된 맵 한 판의 순수 데이터. Environment/pygame 등 다른 모듈에 전혀 의존하지 않으므로
# JSON으로 저장/공유하거나 다른 프로젝트로 그대로 떼어 가도 됨.
#
# objects 항목 형식: {"kind": ..., "id": ..., "x": ..., "y": ..., "params": {...}}
#   kind는 Environment의 add_<kind>() 이름(door/key/button/lever/pressure_plate/item/portal/clue)과
#   같고, params는 그 함수의 나머지 키워드 인자 그대로 (builder.py가 이 규칙으로 배치함)
# objectives 항목 형식: EventLog 항목과 비교할 조건 dict (예: {"type": "door_unlocked", "door_id": "d1"})
#   모든 objective가 한 번씩 충족되면 클리어 (scoring.clear_step 참고)


@dataclass
class MapSpec:
    seed: int
    width: int
    height: int
    walls: list = field(default_factory=list)       # [x, y, width, height] 목록 (맵 좌표, 0~width/height)
    agents: list = field(default_factory=list)      # {"id", "x", "y", "facing"} 목록
    objects: list = field(default_factory=list)     # 위 형식의 오브젝트 목록
    objectives: list = field(default_factory=list)  # 위 형식의 클리어 조건 목록
    puzzles: list = field(default_factory=list)     # 사용된 퍼즐 템플릿 이름 (기록/분석용)
    hints: list = field(default_factory=list)       # 과제 설명에 들어갈 퍼즐별 안내 문장
    config: dict = field(default_factory=dict)      # 생성에 쓰인 GenConfig 값 (재현용)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MapSpec":
        return cls(**data)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "MapSpec":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
