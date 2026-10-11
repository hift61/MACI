# 변경 사항 정리: 시나리오 맵 12종 추가

> 팀원 공유용 문서입니다. 무엇이 추가되고 바뀌었는지, 기존 코드에 영향이 있는지, 어떻게 쓰는지를 한곳에 모았습니다.
> 기준 커밋: `5c1df12` (main).

## 0. 받는 방법 (main에 병합하지 않고 파일만 가져오기)
`scenarios-maps` 브랜치에는 **새로 만든 파일만** 들어 있습니다. 기존 파일의 수정 사항(5절 표의 6개)은 브랜치에 커밋하지 않았습니다. 대신 패치 파일 하나(`scenarios/integration.patch`)로 묶어 두었습니다. 그래서 내 작업 브랜치에서 필요한 파일만 골라 받고, 패치는 직접 적용하면 됩니다.

```powershell
git fetch origin
# 1) 새 파일 가져오기 (내 브랜치는 그대로, 파일만 추가됨)
git checkout origin/scenarios-maps -- scenarios tests/test_scenarios.py TEAM_CHANGES.md map_datas
# 2) 기존 파일 수정분 적용 (spec.py, builder.py, editor_model.py, scoring.py, INTERFACE.md, README.md)
git apply --3way scenarios/integration.patch
# 3) 확인
python -m unittest discover -s tests
python -m scenarios --check
```
- 1단계만 하고 2단계를 빼면 맵 JSON을 읽을 수 없습니다. `MapSpec`에 `scenario`/`rules`/`briefings` 필드가 없기 때문입니다. 반드시 패치까지 적용해 주세요.
- 내 쪽에서 같은 파일을 이미 고쳤다면 `--3way`가 충돌 위치를 표시해 줍니다. 그 부분만 직접 합치면 됩니다.
- 4개 코드 파일(spec.py, builder.py, editor_model.py, scoring.py)의 변경은 합쳐서 50줄 정도입니다. 손으로 옮겨도 됩니다.

## 1. 한 줄 요약
협력 능력을 측정하는 **고난도 맵 12종**을 `scenarios/` 패키지로 추가하고, 런처에서 바로 고를 수 있도록 `map_datas/`에 맵 파일로 넣었습니다.
- 기존 `Environment`는 **수정하지 않고** 상속해서 새 물체와 규칙을 더했습니다.
- 기존 맵과 기존 테스트 64개는 그대로 동작합니다.

## 2. 바로 써 보기
| 목적 | 방법 |
|---|---|
| 런처에서 실행 | `python launcher.py` → **맵** 탭 목록에서 `s01_deadlock.json` 등 선택 → **실행** 탭에서 최대 step을 권장값(아래 표) 이상으로 → 에피소드 실행 |
| 명령행 실행 | `python benchmark.py --map-file map_datas/s01_deadlock.json --steps 120` |
| API 키 없이 동작만 확인 | 위 명령에 `--policy tooluse` (규칙 기반 정책이라 풀지는 못하고, 오류 없이 도는지만 확인) |
| 맵이 실제로 풀리는지 검증 | `python -m scenarios --check` |
| 맵 파일 다시 만들기 | `python -m scenarios` (코드 기준으로 `map_datas/sNN_*.json` 12개를 덮어씀) |
| 테스트 | `python -m unittest discover -s tests` (기존 64 + 새 17 = 81개) |

| 파일 | 이름 | 무엇을 측정하나 | 권장 step |
|---|---|---|---|
| s01_deadlock | 교착 상태 | 대칭 교착을 깨는 순서 합의 | 120 |
| s02_leapfrog | 징검다리 교대 | 판 밟기/통과 역할 10회 교대 | 200 |
| s03_split_experiment | 나눠 보는 실험 | 숨은 XOR 배선을 관찰을 합쳐 추론 | 150 |
| s04_half_mastermind | 반쪽 마스터마인드 | 입력자와 결과 보는 사람이 나뉜 추론 | 200 |
| s05_lossy_sync | 확인의 문제 | 메시지 손실/지연 속 동시 행동 약속 | 150 |
| s06_short_radio | 짧은 무전 | 10자/5 step 제한에서 압축 규약 | 200 |
| s07_me_vs_us | 나 vs 우리 | 개인 보너스 vs 팀 목표 (협력 점수 검증용) | 120 |
| s08_boring_role | 지루한 역할 | 점수 없는 필수 역할의 분담과 공정성 | 200 |
| s09_shared_budget | 공동 예산 | 정보를 합쳐 동선 나누기 (총 이동거리) | 150 |
| s10_moving_world | 움직이는 세계 | 주기 추론과 미래 시점 약속 | 150 |
| s11_pincer | 포위 | 움직이는 목표를 함께 매복해 붙잡기 | 200 |
| s12_unreliable_eyes | 믿을 수 없는 눈 | 서로 다르게 틀린 정보의 교차 검증 | 120 |

**맵별 목표, 의도, 단서와 화면에 나오는 내용, 정답 흐름은 [scenarios/SCENARIOS.md](scenarios/SCENARIOS.md)에 있습니다.**

## 3. 공통 설계 원칙
- **실패가 없습니다.** 함정, 영구 봉인, 횟수 제한 실패를 쓰지 않습니다. 틀리면 다음 중 하나로 **시간만** 잃습니다.
  - 패널 초기화
  - 밀려나기
  - 문 닫힘
  - 다음 주기까지 대기
- **갇히지 않습니다.** 어떤 상태에서든 다시 클리어할 수 있습니다.
- 모든 맵을 **정답 스크립트**와 **일부러 실수한 뒤 복구하는 스크립트**로 실제로 클리어되는지 확인했습니다(아래 6절).
- 난이도는 "숨긴 정보" 수준이 아니라 **함께 계획, 추론, 약속하지 않으면 안 풀리는 구조**에서 나옵니다. 대부분 방이 벽으로 나뉘어 있어 메시지 없이는 풀 수 없습니다.

## 4. 새로 추가된 파일
| 경로 | 내용 |
|---|---|
| `scenarios/__init__.py` | 시나리오 목록(`SCENARIO_NAMES`), `load()`, `all_scenarios()` |
| `scenarios/engine.py` | **ScenarioEnvironment**: `Environment`를 상속해 새 물체 15종과 메시지/유리벽 규칙을 더함 (아래 5절) |
| `scenarios/common.py` | 맵 조립 도구(벽, 물체, MapSpec), 새 물체의 영어 설명문 |
| `scenarios/oracle.py` | 정답 검증용 스크립트 정책 (테스트 전용, LLM 무관) |
| `scenarios/s01_deadlock.py` … `s12_unreliable_eyes.py` | **시나리오 하나당 파일 하나**: `build()`(맵), `solution()`, `mistake()`(검증용) |
| `scenarios/__main__.py` | `python -m scenarios` (내보내기, `--check`, `--list`) |
| `scenarios/SCENARIOS.md` | 시나리오 설명서 (목표, 의도, 단서/화면 내용, 정답 흐름, 실수 시) |
| `scenarios/integration.patch` | 기존 파일 6개의 수정 사항 (5절). `git apply --3way`로 적용 |
| `map_datas/s01_deadlock.json` … `s12_unreliable_eyes.json` | 런처에서 바로 고르는 맵 파일 12개 |
| `tests/test_scenarios.py` | 시나리오 테스트 17개 |
| `TEAM_CHANGES.md` | 이 문서 |

## 5. 수정된 기존 파일 (모두 하위 호환)
| 파일 | 바뀐 내용 | 기존 동작 영향 |
|---|---|---|
| `mapgen/spec.py` | `MapSpec`에 필드 3개 추가: `scenario`(시나리오 이름), `rules`(환경 규칙), `briefings`(에이전트별 추가 안내문) | 없음. 기본값이 있어서 예전 맵 JSON도 그대로 읽힘 |
| `mapgen/builder.py` | `scenario`나 `rules`가 있으면 `ScenarioEnvironment`로 생성. 에이전트 항목에 `view_radius`/`view_angle`이 있으면 전달. `briefings`를 과제 설명 끝에 붙임 | 없음. 일반 맵은 여전히 `Environment` (테스트로 확인) |
| `mapgen/editor_model.py` | `finalize()`: 시나리오 맵이면 직접 쓴 `hints`/`config`를 유지 (자동 안내로 덮어쓰지 않음) | 없음. 일반 맵은 기존과 같음 |
| `enviroment/scoring.py` | 새 이벤트 배점과 `team.metrics` 추가 (아래 표) | 기존 이벤트 배점은 그대로. `metrics`는 총점에 안 들어감 |
| `INTERFACE.md` | MapSpec/builder/editor_model/scoring 항목 갱신, `scenarios/` 절 추가 | - |
| `README.md` | "시나리오 맵" 소절 추가 | - |

**`enviroment/enviroment.py`, `policy.py`, `benchmark.py`, `launcher.py`, `viewer.py`는 수정하지 않았습니다.** 런처는 원래 `map_datas/*.json`을 목록에 띄우므로 수정 없이 맵이 나타납니다.

### 채점(scoring.py) 추가 사항
| 이벤트 | 개인 점수 | 설정 이름 |
|---|---|---|
| `bonus_collected` (보너스 아이템 습득) | 아이템에 정한 점수 (s07 25점, s08 10점) | (아이템별) |
| `item_delivered` (회수함에 배달) | +5 | `delivery_points` |
| `checkpoint_visited` | +3 | `checkpoint_points` |
| `keypad_solved` (패널 풀기, 마지막 입력자) | +10 | `keypad_points` |
| `sync_success` (동시 진입 성공, 전원) | +10 | `sync_points` |

- `press_button`의 성공 판정에 `keypad_input`을 추가했습니다. 그래서 패널 버튼 누르기가 "헛된 시도"로 세지지 않습니다.
- `score.json`의 `team.metrics`(시나리오 맵에서만): 아래 값들이 들어갑니다.
  - `distance_travelled`, `team_distance`: 에이전트별, 팀 전체 이동거리
  - `plate_hold_steps`: 판 위에 있었던 step 수
  - `bonus_points`: 보너스 점수
  - `messages`: 손실, 지연, 거부 횟수

### 새 물체와 규칙 (자세한 인터페이스는 INTERFACE.md "scenarios/" 절)
- **물체**: 아래 15종입니다. 이름이 `_`로 시작하는 필드(정답 코드, 배선, 주기 등)는 관찰에서 자동으로 지워집니다.
  - `goal_zone`, `switch_plate`(OR 압력판), `latch_lever`(영구 개방 레버)
  - `logic_door`(숨은 XOR 배선 문), `switch_lever`(재사용 대기시간 레버)
  - `keypad`, `keypad_button`, `display`
  - `sync_pad`(동시 진입 판), `periodic_door`(주기 문)
  - `bonus_item`, `spawner`, `receptacle`(회수함), `checkpoint`
  - `variant_clue`(에이전트마다 다르게 보이는 단서)
  - 기존 `mover`의 경로 숨기기 옵션
- **규칙**(`MapSpec.rules`): 아래 규칙들이 있습니다. 손실과 지연은 시드로 재현됩니다.
  - `message_loss`, `message_delay`: 메시지 손실, 지연
  - `message_max_chars`, `message_interval`: 길이와 빈도 제한
  - `glass_walls`: 이동은 막고 시야는 통과
- **새 이벤트**: `team_assembled`, `keypad_*`, `sync_*`, `bonus_*`, `item_spawned`, `item_delivered`, `delivery_complete`, `checkpoint_visited`, `all_checkpoints_visited`, `message_lost`, `message_blocked`, `lever_cooling`

## 6. 검증 결과
- `python -m scenarios --check`: 12개 맵 × (정답, 실수 후 복구) = 24회 모두 클리어.

  | 맵 | 정답 | 실수 후 | 맵 | 정답 | 실수 후 |
  |---|---|---|---|---|---|
  | s01 | 35 | 69 | s07 | 33 | 52 |
  | s02 | 125 | 136 | s08 | 74 | 91 |
  | s03 | 15 | 22 | s09 | 53 | 53 (이동거리만 증가) |
  | s04 | 28 | 44 | s10 | 43 | 43 (다음 공통 주기에 재시도) |
  | s05 | 20 | 24 | s11 | 112 | 112 |
  | s06 | 46 | 53 | s12 | 53 | 66 |
  - 숫자는 정답을 아는 스크립트의 클리어 step입니다. 즉 이론상 하한이고, LLM은 더 오래 걸립니다.
- `benchmark.py --map-file`로 12개 맵을 `tooluse`, `random` 정책으로 40 step씩 실행했습니다(24회). 오류 없이 끝까지 돌고 점수 파일과 `metrics`가 생성됐습니다.
- 에디터와 리플레이 뷰어에서 12개 맵을 모두 정상적으로 그립니다. 에디터에서 열었다가 저장해도 목표 안내와 규칙이 유지됩니다.
- 전체 테스트 81개(기존 64 + 새 17) 통과.
- **LLM(CodePolicy) 실제 실행은 아직 못 했습니다.** 이 작업 환경에 `key.txt`가 없습니다.

## 7. 알아 둘 점 / 확인 부탁
1. **기다리면 코드를 다시 짜는 문제**: 현재 main(`5c1df12`)의 `CodePolicy._stuck_reason`은 3 step 동안 제자리에 있으면 "막힘"으로 보고 코드를 다시 생성합니다(압력판 위만 예외).
   - 실험해 보니 `noop`이나 `send_message`로 기다려도 3 step마다 재생성되고, 31 step 만에 재생성 한도 10회를 다 씁니다.
   - 이번 맵 중 **기다림이 핵심인 맵**이 영향을 받습니다.
     - s01, s02, s08: switch_plate는 압력판 예외에 해당하지 않음
     - s04: B는 화면만 봄
     - s05, s10: 약속한 step까지 대기
   - 팀원이 고쳤다고 들었는데 아직 원격 main에는 반영되지 않았습니다. 수정본이 올라오면 이 맵들로 같이 확인해 보면 좋겠습니다.
   - 예외 목록에 `switch_plate`/`sync_pad`를 넣는 것도 방법입니다.
2. **새 물체 설명 위치**: `policy.py`의 `_OBSERVATION_DOC`에는 기존 물체만 있습니다. 그래서 새 물체 설명은 각 맵의 과제 설명 끝(`briefings`)에 영어로 붙였습니다. 프롬프트를 손볼 때 공용 설명으로 옮겨도 됩니다(`scenarios/common.py`의 `OBJECT_HELP`).
3. **런처 기본 step은 150**이라, s02, s04, s06, s08, s11(권장 200)은 늘려서 실행해야 합니다.
4. **맵 수정은 `.py` 기준**: JSON을 직접 고치거나 에디터로 저장해도 실행은 됩니다. 하지만 `python -m scenarios`를 다시 돌리면 코드 기준으로 덮어씁니다.
5. `glass_walls`(유리벽) 규칙은 구현과 테스트만 해 두었고, 현재 쓰는 맵은 없습니다.
6. 이전 코드 검수에서 남은 버그 6건은 이번 작업에 포함하지 않았습니다(압력판이 열쇠로 연 문을 다시 잠금, 이미 열린 문에 열쇠 소모 등). 이번 맵들은 그 경로를 쓰지 않습니다.
