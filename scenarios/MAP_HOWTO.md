# 시나리오 맵 만들기: 작성 절차와 레퍼런스

> 이 문서는 **파일을 어떻게 쓰는지**(절차, 물체/목표/규칙 레퍼런스, 검증, 자주 하는 실수)를 다룹니다.
> **어떤 맵을 만들어야 하는지**(합격 기준, 난이도 설계)는 팀원 문서 [MAP_GUIDE.md](MAP_GUIDE.md)를 따릅니다.

새 협력 맵을 `scenarios/`에 추가하는 방법입니다. 이 순서대로 하면 만든 맵이 다음 세 곳에 바로 들어갑니다.
- 런처 맵 목록
- `benchmark.py --map-file`
- 테스트

기존 24개 맵이 모두 이 방식으로 만들어졌으니, 막히면 비슷한 맵의 파일을 열어 보세요(아래 "참고할 맵" 표).

---

## 1. 한눈에: 맵 하나에 필요한 파일

### 새로 만드는 파일 (필수)
| 파일 | 하는 일 | 어떻게 |
|---|---|---|
| `scenarios/sNN_이름.py` | 맵 정의 + 검증 plan | [`scenarios/_template.py`](_template.py)를 복사해서 고침 |
| `map_datas/sNN_이름.json` | 런처/benchmark가 읽는 맵 파일 | **손으로 만들지 않음.** `python -m scenarios sNN_이름`이 생성 |

### 고치는 파일 (필수)
| 파일 | 고칠 곳 |
|---|---|
| `scenarios/__init__.py` | `SCENARIO_NAMES` 목록 끝에 `"sNN_이름"` 추가 |
| `scenarios/SCENARIOS.md` | "한눈에 보기" 표에 한 줄, 맨 아래에 맵 설명 절 하나 (8장의 틀 복사) |

### 고치는 파일 (경우에 따라)
| 이런 경우 | 고칠 파일 |
|---|---|
| 새 물체나 새 규칙이 필요함 | `scenarios/engine.py`(구현), `enviroment/policy.py`(`_OBSERVATION_DOC`의 Object roles 한 줄), `INTERFACE.md`("scenarios/" 절), `SCENARIOS.md` 0장 표, `tests/test_scenarios.py`(동작 테스트) - 7장 |
| 새 이벤트에 점수를 주고 싶음 | `enviroment/scoring.py`의 `ScoreConfig`와 `_individual_points`, `INTERFACE.md` scoring 절 |
| 실수 스크립트에서 반드시 나와야 하는 이벤트를 테스트로 고정하고 싶음 | `tests/test_scenarios.py`의 `test_mistakes_really_happen_and_cost_time`의 `expected` |
| 팀 공유 | `TEAM_CHANGES.md` 4절 표 |

### 읽기만 하는 파일 (참고용)
| 파일 | 왜 보나 |
|---|---|
| `scenarios/common.py` | `obj`, `agent`, `hwall`, `vwall`, `stage`, `make_spec` 사용법과 정보 전달 원칙 주석 |
| `scenarios/engine.py` 맨 위 설명 | 시나리오 전용 물체와 규칙 목록 |
| `scenarios/oracle.py` 맨 위 설명 | 검증 plan 항목 형식 |
| `enviroment/enviroment.py`의 `add_*` | 기존 물체(문, 열쇠, 버튼, 레버, 압력판, 아이템, 포탈, 단서, mover) 인자 |
| `enviroment/environment_prompt.py` | 모든 에이전트가 공통으로 받는 설명 (시야 200, 90도 등) |

### 참고할 맵
| 만들고 싶은 것 | 참고 |
|---|---|
| 방을 벽으로 나누고 문/판으로 오가기 | s01_deadlock, s02_leapfrog |
| 숨은 규칙을 관찰로 추론 | s03_split_experiment (logic_door) |
| 패널에 코드 입력, 결과 화면 | s04_half_mastermind (mastermind), s06/s12 (sequence) |
| 메시지 규칙 (손실, 지연, 길이 제한) | s05_lossy_sync, s06_short_radio |
| 2인 운반, 회수함 배달 | s07_me_vs_us, s11_pincer |
| 시간이 지나면 생기는 아이템, 개인 보너스 | s08_boring_role |
| 에이전트마다 다른 정보 | s09_shared_budget, s12_unreliable_eyes (variant_clue) |
| 동시 행동, 주기 문 | s05_lossy_sync, s10_moving_world (sync_pad, periodic_door) |
| 움직이는 목표 | s11_pincer (mover + `_hide_path`) |
| 유리벽 너머 원격 조작, 일부 에이전트만 도착하면 되는 목표 | s16_remote_maze (glass_walls, goal_zone `agents`) |
| 함께 밀어야 하는 블록, 리셋 | s17_push_blocks (push_block, block_target, reset_lever) |
| 가공/생산 라인, 유리 창구로 물건 주고받기 | s18_assembly_line (station, glass_walls) |
| 들고 있을 수 있는 시간 제한, 이어 달리기 | s19_hot_cargo (cargo) |
| 숨은 수치를 재서 조합 맞추기 | s20_scales (weighted_item, scale) |
| 메시지 금지, 특정 에이전트만 조작 | s21_silent_signs (message_disabled, keypad `operators`, marker) |
| 한 명만 들어갈 수 있는 구역 | s22_narrow_bridge (capacity_zone) |
| 열쇠로 여는 상자, 의존 관계 | s23_key_chests (chest) |
| 공용 비용과 개인 점수 (동전, 통행료) | s24_shared_purse (coin, receptacle `opens`) |

---

## 2. 만드는 순서

```text
설계 → 템플릿 복사 → build() 작성 → 검증 plan 작성 → 등록 → --check → 내보내기 → 문서 → 테스트
```

1. **설계**: 9장의 설계 체크리스트를 먼저 봅니다. 맵마다 아래 다섯 가지를 한 줄씩 정해 두세요. 이것이 그대로 문서 내용이 됩니다.
   - 측정할 협력 능력(의도)
   - 클리어 조건
   - 누가 무엇을 아는지
   - 실수하면 무슨 일이 일어나는지
   - 왜 혼자서는 안 되는지
2. **템플릿 복사**:
   ```powershell
   Copy-Item scenarios\_template.py scenarios\s25_my_map.py
   ```
   파일 맨 위의 `NAME`을 파일 이름(`"s25_my_map"`)과 똑같이 바꾸고, `TITLE`과 `FAMILY`도 고칩니다.
3. **`build()` 작성**: 다음 순서로 채웁니다(3~6장). `make_spec(...)`이 맵 데이터를 만들어 줍니다.
   - 벽 → 물체 → 단서 → 클리어 조건(objectives) → 목표 요약(hints, 기록용) → 규칙(rules). 단계형이면 `stage(...)`로 단계마다
4. **검증 plan 작성**: `solution(env)`(정답)과 `mistake(env)`(실수한 뒤 복구)를 씁니다(8장). 다른 사람이 풀 수 있는 맵인지 확인하는 유일한 방법이니 꼭 둘 다 작성하세요.
5. **등록**: `scenarios/__init__.py`의 `SCENARIO_NAMES`에 `"s25_my_map"`을 추가합니다.
6. **검증**:
   ```powershell
   python -m scenarios s25_my_map --check
   ```
   `solution`과 `mistake`가 모두 `cleared at step N`이 나와야 합니다. 이 명령이 통과하면 `map_datas/s25_my_map.json`도 같이 만들어집니다.
7. **눈으로 확인**: 에디터에서 열어 배치를 보고, `P`로 직접 조작해 봅니다(10장).
8. **문서**: `SCENARIOS.md`에 표 한 줄과 설명 절을 추가합니다(11장 틀).
9. **테스트**:
   ```powershell
   python -m unittest tests.test_scenarios
   ```
   새 맵은 `SCENARIO_NAMES`에 넣는 것만으로 다음 테스트 대상이 됩니다.
   - 풀림
   - 실수 후 풀림
   - 실패 상태 없음
   - JSON 왕복
   - 내보낸 파일과 코드의 일치

---

## 3. 물체 레퍼런스 (`obj(kind, id, x, y, **params)`)

`kind`는 `Environment.add_<kind>`의 이름이고, 나머지 키워드는 그 함수 인자입니다. **관찰 type**은 에이전트가 보는 `type` 값입니다.

### 기존 물체 (enviroment.py)
| kind | 주요 params | 관찰 type | 동작 |
|---|---|---|---|
| `door` | `locked=True`, `radius=10`, `hidden=False` | door | 잠긴 동안 반경 안으로 이동 불가 |
| `key` | `unlocks` | key | 주워서 `use_key`로 문을 엶 (사라짐) |
| `button` | `linked_door_id` | button | 누를 때마다 문 열림/닫힘 전환 |
| `lever` | `linked_door_ids` | lever | 당길 때마다 on/off, 문 여러 개 |
| `pressure_plate` | `linked_door_id`, `radius=10` | pressure_plate | 밟는 동안 열림. 같은 문에 여러 개면 **전부** 밟아야 함(AND) |
| `item` | `category="normal"`/`"coop"`, `required_agents=2` | item | coop은 둘이 15 이내에 있어야 줍고 옮김. (`"trap"`은 실패 상태를 만들므로 시나리오에서 쓰지 않음) |
| `portal` | `dest_x`, `dest_y`, `radius=10` | portal | 들어서면 순간이동 |
| `clue` | `content`, `hidden=True` | clue | 읽을 내용. hidden이면 15 이내에서만 보임 |
| `mover` | `waypoints`, `speed`, `object_type`, `loop`, `extra` | (object_type) | 매 step 경로를 따라 움직임. `extra={"_hide_path": True}`로 경로 숨김 |

### 시나리오 전용 물체 (scenarios/engine.py)
| kind | 주요 params | 관찰 type | 동작 |
|---|---|---|---|
| `goal_zone` | `width`, `height`, `label`, `agents=None` | goal_zone | 사각형(x, y는 중심). 전원(또는 `agents`의 에이전트)이 동시에 안에 있으면 `team_assembled` |
| `switch_plate` | `opens=[문들]`, `radius=10` | switch_plate | 밟는 동안 열림. 한 문에 여러 개면 **하나만** 밟아도 됨(OR) |
| `latch_lever` | `doors=[문들]` | lever | 당기면 영구 개방 (판이 다시 못 잠금) |
| `logic_door` | `levers=[레버들]`, `parity=1`, `radius=12` | door | 연결 레버 ON 개수 % 2 == parity면 열림 (배선은 비밀) |
| `switch_lever` | `cooldown=0`, `label` | lever | logic_door용. 당긴 뒤 cooldown step 재사용 불가 |
| `keypad` | `code=[라벨들]`, `mode="sequence"`/`"mastermind"`, `display_id`, `opens`, `operators=None` | keypad | 패널. 정답 코드는 비밀. `operators`가 있으면 그 에이전트만 누를 수 있음 |
| `keypad_button` | `panel`, `label` | button | `press_button`으로 패널에 `label` 입력 |
| `display` | `content`, `label` | display | 엔진이 갱신하는 화면 (mastermind 결과 등) |
| `sync_pad` | `group`, `tolerance=0`, `return_x/y`, `cooldown=3`, `opens` | sync_pad | 같은 그룹을 tolerance step 이내에 모두 진입하면 성공, 혼자면 밀려남 |
| `periodic_door` | `period`, `open_steps`, `phase=0` | door | (step+phase) % period < open_steps일 때 열림 (주기는 비밀) |
| `bonus_item` | `points`, `expires_at` | item | 주우면 개인 보너스, expires_at에 사라짐 |
| `spawner` | `area=[x0,y0,x1,y1]`, `every`, `max_alive`, `prefix`, `points`, `label` | (안 보임) | 영역에 `<prefix>_<n>` 아이템을 주기적으로 생성 (`x`, `y`는 0, 0) |
| `receptacle` | `accepts=[id 접두사]`, `target`, `radius=20`, `label`, `opens=[문들]` | receptacle | 반경 안에 맞는 아이템을 drop하면 회수. 목표 수에 도달하면 `opens`의 문을 영구히 엶 (통행료 함) |
| `checkpoint` | `radius=12`, `hidden=False`, `label` | checkpoint | 누군가 들어가면 방문 처리 |
| `variant_clue` | `content`, `variants={agent_id: 내용}`, `hidden` | clue | 에이전트마다 다른 내용 |
| `push_block` | `radius=12`, `required=2`, `push_distance=20` | block | 단단한 블록. required명이 같은 step에 같은 방향(30도 이내)으로 걸어 들어가면 그 방향으로 밀림 |
| `block_target` | `radius=10`, `label` | block_target | 블록 중심이 반경 안이면 filled. 전부 채워지면 `all_targets_filled` |
| `reset_lever` | `blocks=[블록들]` | lever | 당기면 블록들이 처음 자리로 |
| `station` | `input`, `output`, `process_steps=3`, `radius=15`, `out_x`, `out_y` | station | input 접두사 아이템을 drop하면 process_steps 뒤 `<output>_...` 아이템 생성 (한 번에 하나) |
| `cargo` | `hold_limit=10`, `carry_speed=10` | item | 한 사람이 hold_limit step 넘게 가지면 원위치. 들면 느려짐. **다른** 사람이 집어야 시간 초기화 |
| `weighted_item` | `weight`, `label` | item | 숨은 무게 (scale로만 확인) |
| `scale` | `radius=15`, `target=None` | scale | 반경 안 무게 합을 `reading`에. target이 있으면 too light / too heavy / balanced만 |
| `capacity_zone` | `width`, `height`, `capacity=1` | capacity_zone | 정원을 넘으면 안의 전원을 들어오기 전 자리로 |
| `chest` | `contents=[{"kind", "id", ...}]`, `radius=8` | chest | `unlocks`가 이 상자인 열쇠로 `use_key` → 내용물이 옆에 생김 |
| `coin` | `value=5` | item | 회차가 끝날 때 들고 있는 동전 가치가 개인 점수 |
| `marker` | `label`, `radius=12` | marker | 동작 없는 바닥 표시 (물건을 올려 신호로) |

**비밀 값**: params 이름이 `_`로 시작하면 관찰에서 지워집니다(예: mover의 `extra={"_hide_path": True}`). 정답 코드, 배선, 주기는 엔진이 알아서 `_`로 저장하므로 따로 신경 쓰지 않아도 됩니다.

### 에이전트 (`agent(id, x, y, facing)`)
- 좌표는 맵 좌표(0~width, 0~height)이고 y는 아래로 갈수록 커집니다. facing: 0=오른쪽, 90=아래, 180=왼쪽, 270=위.
- 시야를 다르게 주려면 dict에 키를 추가합니다. 예: `{**agent("A", 30, 30), "view_radius": 40}` (기본 200, 각도 90).

### 벽
- `[x, y, w, h]` 목록입니다. 벽은 이동과 시야를 모두 막습니다(유리벽은 5장 규칙).
- `vwall(x, y0, y1, gaps=[(가운데 y, 폭)])`, `hwall(y, x0, x1, gaps=[(가운데 x, 폭)])`는 두께 10짜리 벽을 만들고 gaps 자리를 비웁니다.
- **문 끼우기 공식**: 폭 20인 틈 가운데에 `radius=12` 문을 두면 잠긴 동안 지나갈 수 없습니다. 예: `vwall(150, 0, 200, gaps=[(100, 20)])` + `obj("door", "gate", 155, 100, radius=12.0)`. 문 x는 벽 x + 5입니다.

---

## 4. 클리어 조건 레퍼런스 (`objectives`)

`objectives`의 dict 하나하나가 EventLog 이벤트와 **키/값이 모두 같으면** 충족됩니다. 전부 충족된 step이 클리어 step입니다. 여러 개를 넣으면 모두 달성해야 합니다(예: s06은 패널 두 개).

| 목표 | objective | 이벤트를 만드는 물체 |
|---|---|---|
| 전원이 한 구역에 모임 | `{"type": "team_assembled", "zone_id": "exit"}` | goal_zone |
| 문 열기 | `{"type": "door_unlocked", "door_id": "gate"}` | door 계열 전부 |
| 아이템 줍기 | `{"type": "item_picked_up", "object_id": "crate"}` | item |
| 패널 풀기 | `{"type": "keypad_solved", "panel_id": "panel"}` | keypad |
| 동시 진입 성공 | `{"type": "sync_success", "group": "sync"}` | sync_pad |
| 회수함 목표 수 달성 | `{"type": "delivery_complete", "receptacle_id": "dock"}` | receptacle |
| 체크포인트 전부 방문 | `{"type": "all_checkpoints_visited"}` | checkpoint |
| 목표 칸 전부 채움 | `{"type": "all_targets_filled"}` | block_target |
| 저울 정확히 맞춤 | `{"type": "scale_balanced", "scale_id": "vault_scale"}` | scale (target 있음) |

- `hints`에는 같은 목표를 **영어 문장**으로 씁니다. 목표 공개 실행(`--hide-goal`을 안 쓴 경우)에서 "Goal: …"로 에이전트에게 보입니다.
- 목표를 숨긴 실행에서도 맵 안 단서와 단계 안내는 보입니다. 목표 숨김 실험에 쓸 맵이면 단서에 목표를 직접 쓰지 마세요.

---

## 5. 규칙 레퍼런스 (`rules`)

| 키 | 예 | 효과 |
|---|---|---|
| `message_loss` | `0.35` | 메시지가 이 확률로 조용히 사라짐 |
| `message_delay` | `[0, 2]` | 메시지가 0~2 step 늦게 도착 |
| `message_max_chars` | `10` | 본문이 10자를 넘으면 거부 (보낸 사람에게 system 알림) |
| `message_interval` | `5` | 한 사람이 5 step에 한 번만 전송 |
| `message_disabled` | `true` | 메시지를 아예 보낼 수 없음 |
| `glass_walls` | `[[100, 0, 10, 200]]` | 이동은 막고 시야는 통과하는 벽 (`walls`와 별도로 적음) |
| `seed` | `11` | 손실/지연/아이템 생성 난수 시드 (같은 값이면 같은 결과) |

규칙이 없으면 `rules={}`로 둡니다. 메시지 규칙을 쓰는 맵은 단서에 규칙을 알려 주세요(s06 참고). 규칙을 일부러 숨기는 맵도 있습니다(s05).

---

## 6. 에이전트가 읽는 글 쓰기 (정보 전달 원칙, 2026-10-13 결정)

모든 맵에 같은 원칙을 씁니다. **모두 영어로** 씁니다.

| 어디 | 무엇을 쓰나 | 쓰지 않는 것 |
|---|---|---|
| 시스템 프롬프트 (`enviroment/policy.py`의 `_OBSERVATION_DOC`, 모든 맵 공통) | **모든 물체 종류의 역할** (문, 열쇠, 판, 패널, 회수함, 블록 등)과 `stage`, `reward` 관찰 필드 | 특정 맵 이야기 |
| 과제 설명 (맵별) | **목표 문장만**: `objectives`가 `environment_prompt.objective_description`에서 "Goal: open keypad 'x'." 같은 문장으로 바뀜. 그 뒤에 공통 문장(`COMMON_RULES`) | 위치, 누가 어디 있는지, 역할 분담, 단서 읽기 지시, 물체 설명 (`briefings`는 주지 않는 것이 기본) |
| 단계 안내 (`stage(title, briefing, ...)`의 briefing) | 그 단계의 **목표만** (예: "Open panel_2.", "Both of you stand inside yard_1 at the same time.") | 위치, 전략 |
| 단서(`clue`), 화면(`display`), 이름표(`label`) | **퍼즐 자료**(코드, 숫자, 좌표 목록)와 **직접적이고 구체적인 힌트**(힌트 버전만. 예: "The plate in a room holds open the door of the OTHER room, not its own.", "If only one pad is entered, whoever stands on a pad is pushed back and both pads ignore entries for a few steps.", "A copy of the code. Copies may contain mistakes.") | **현재 상태**(지금 잠겨 있다 등), **위치/배치**("북동쪽 구석에", "방 B에"), **해결 전략**("팀원에게 알려라", "번갈아 밟아라", "이 쪽지는 상대를 위한 것") |

- 기준점 (2026-10-13 최종): **힌트 버전**의 단서는 이 맵 장치가 어떻게 작동하는지 **직접적이고 구체적으로** 알려 줍니다
  (어느 판이 어느 문을 여는지, 실패 시 벌칙, 속도, 화면 값의 뜻, 정보가 틀릴 수 있다는 것, 이 쪽지가 어느 패널의 코드인지).
  **힌트 없는 버전**은 그 문장을 모두 빼고 퍼즐 자료만 남깁니다. 두 버전 모두 "B에게 물어봐라", "번갈아 밟아라" 같은
  해결 순서 지시는 쓰지 않습니다.
- 퍼즐 자료는 단서에 그대로 둡니다(코드, 합계, 좌표, 목표 무게). 자료에는 이름만 붙입니다(`{"copy of the code": "5 7 8"}`).
- **두 버전 (2026-10-13)**: 맵마다 `map_datas/<이름>.json`(단서에 규칙 힌트 있음)과 `map_datas/<이름>_nohint.json`(퍼즐 자료만)이 함께 나옵니다. `common.without_clue_hints`가 단서 content에서 `CLUE_DATA_KEYS`(code, copy of the code, sum of the digits, checkpoints, target weight of vault_scale) 밖의 키를 지우고, 남는 것이 없는 단서는 뺍니다. 그래서 **퍼즐 자료는 반드시 이 키 중 하나로**, 규칙 문장은 다른 키(`hint`, `plates`, `screen` 등)로 씁니다. 새 자료 키가 필요하면 `CLUE_DATA_KEYS`에 추가하세요. 문자열 content(variant_clue)는 자료로 보고 그대로 남습니다. `--check`는 두 버전을 모두 검증하고, 테스트(`ClueHintVersionTests`)가 기본 버전에 규칙 문장이 있는지, _nohint 버전에 자료 키만 있는지 확인합니다. 실행 때 `benchmark.py --no-clue-hints`로도 어떤 맵이든 힌트 없는 버전으로 돌릴 수 있습니다.
- 이름표(`label`)에도 위치를 쓰지 않습니다(`"room A test scale"` 대신 `"test scale"`).
- `hints`(MapSpec)는 사람이 읽는 목표 요약일 뿐 에이전트에게 가지 않습니다. 목표는 `objectives`에서 만들어집니다.
- `explain()`과 `STAGE_RULES`는 예전 맵 호환용으로만 남아 있고, 새 맵에서는 쓰지 않습니다(같은 내용이 시스템 프롬프트에 있음).
- 정보 비대칭을 만들려면 다음 중 하나를 씁니다.
  - 단서를 **다른 방**에 둡니다(벽이 시야를 가림).
  - `hidden=True`로 가까이 가야만 보이게 합니다.
  - `variant_clue`로 사람마다 다르게 보이게 합니다.
- 단서 내용에 정답을 직접 쓰지 말고, **풀기 위해 협력이 필요한 조각**만 주세요.
- 실제로 전달되는 글은 `python -m scenarios --texts`로 [AGENT_TEXTS.md](AGENT_TEXTS.md)에 만들어 확인합니다. 테스트(`test_task_descriptions_give_only_the_goal`)가 과제 설명에 위치어나 물체 설명이 들어가면 실패합니다.

---

## 7. 새 물체/규칙이 필요할 때

기존 물체로 안 되는 경우에만 `scenarios/engine.py`를 고칩니다. `enviroment/enviroment.py`(원본)는 고치지 않습니다.

1. `engine.py`에 `add_<kind>(self, <id>, x, y, ...)`를 추가합니다.
   - `self.objects[id] = {"object_id", "x", "y", "type", ...}` 형식입니다.
   - 관찰에 보이면 안 되는 값은 `_이름`으로 저장합니다.
2. 동작을 붙입니다. 어느 훅에 붙일지는 동작 종류로 정합니다.
   | 동작 | 붙이는 곳 |
   |---|---|
   | 매 step 시작 (시간에 따른 변화) | `_update_movers()` |
   | 매 step 끝 (위치 판정) | `_update_pressure_plates()` |
   | 행동에 반응 | `press_button`, `pull_lever`, `pick_up`, `drop`, `apply_action` 오버라이드 |
3. 일어난 일은 `self._log("이벤트_이름", [원인 agent_id들], 필드=값)`으로 기록합니다. 클리어 조건과 채점은 이 이벤트를 봅니다.
4. 실패 상태를 만들지 마세요. 틀리면 리셋, 밀려남, 대기만 일어나야 합니다.
5. `enviroment/policy.py`의 `_OBSERVATION_DOC` "Object roles"에 영어 역할 설명 한 줄을 추가합니다(모든 맵 공통). `tests/test_scenarios.py`의 `test_system_prompt_explains_every_object_type` 목록에도 type을 추가합니다.
6. `tests/test_scenarios.py`에 동작 테스트를 추가합니다(`ScenarioRuleTests` 참고).
7. `INTERFACE.md`의 "scenarios/engine.py" 절(물체/이벤트 목록)과 `SCENARIOS.md` 0장 표에 추가합니다.

---

## 8. 검증 plan 쓰기 (`solution`, `mistake`)

`oracle.py`가 plan대로 에이전트를 움직여 실제로 클리어되는지 봅니다. LLM과 무관한 **설계 검증용**입니다.

| 항목 | 뜻 |
|---|---|
| `("goto", x, y)` | 그쪽으로 돌고 20씩 전진 (도착하면 다음) |
| `("face", deg)` | 그 방향으로 회전 |
| `("act", {...})` | 행동 한 번. 예: `{"type": "press_button", "button_id": "btn"}`, `{"type": "pull_lever", "lever_id": "L1"}`, `{"type": "pick_up", "object_id": "crate"}`, `{"type": "drop", "object_id": "crate"}`, `{"type": "move_forward", "distance": 20}` |
| `("wait", n)` | n step 대기 |
| `("at_step", n)` | step n까지 대기 (동시 행동 약속용) |
| `("until", lambda e: 조건)` | 조건이 참이 될 때까지 대기. `oracle.unlocked("door")`, `oracle.near(e, "A", x, y)` 사용 가능 |
| `("barrier", "이름")` | 모든 에이전트가 도착하면 다음 step에 함께 출발 |
| `("call", fn)` | `fn(env, agent_id, obs)`가 행동을 돌려주는 동안 반복 (예: 생긴 아이템 줍기, s08) |
| `("lock", "이름")` / `("unlock", "이름")` | 한 번에 한 에이전트만 지나가는 구간 (s19 다리) |

`call`용으로 `oracle.fetch(prefix, count=1, region=None, where=None)`(접두사 물건을 count개 들 때까지 가까운 것부터 줍기)와 `oracle.drop_prefix(prefix, count=None)`(접두사 물건 내려놓기)가 있습니다. `until`용으로 `oracle.lying(prefix, region)`(그 영역 바닥에 물건이 있는지)이 있습니다. 동적으로 생기는 아이템(s08, s15, s19)이나 여러 개를 줍는 맵(s18, s21)에서 씁니다.

- **2인 운반**: `oracle.carry_legs(출발점, [경유점들])`로 두 사람의 plan을 똑같이 만들고, 앞에 `("barrier", ...)`를 둡니다(s07, s11).
- **`mistake`는 실제로 시간을 잃어야** 의미가 있습니다. `--check` 결과에서 실수 쪽 step이 정답보다 커야 합니다. 같다면 실수가 아무 영향을 주지 않은 것입니다.
- 정답 plan은 **이론상 가장 빠른 풀이**입니다. 권장 step(`recommended_steps`)은 그 3~5배 정도로 잡습니다. LLM은 탐색, 대화, 추론에 시간이 걸립니다.

---

## 9. 설계 체크리스트

**규칙** (지키지 않으면 테스트가 실패하거나 실험이 무의미해짐)
- [ ] 실패 상태가 없다. trap 아이템, 영구 봉인을 쓰지 않는다(`test_no_failure_state_is_ever_reached`).
- [ ] 어떤 실수를 해도 갇히지 않는다. 닫힌 곳에 들어간 사람은 상대가 다시 열어 주면 나올 수 있다.
- [ ] 혼자서는 풀 수 없다. 정보, 위치, 동시 행동 중 적어도 하나가 상대에게 달려 있다.
- [ ] 과제 설명과 단계 안내는 목표만 말하고, 단서는 퍼즐 자료(자료 키)와 구체적인 힌트(다른 키)로 나뉜다 (6장). 새 물체 type은 시스템 프롬프트에 역할이 있다.

**수치** (환경 기본값: 시야 200·90도, 상호작용 15, 한 번에 최대 20 이동, 압력판·패드 반경 10)
- [ ] 판 위에서 그 문을 지나갈 수 없을 만큼 판이 문에서 멀다 (문 반경 + 15 이상).
- [ ] "안 보여야 하는 것"은 거리(200 이상)나 **벽**으로 가린다. 시야가 넓어서 거리만으로는 잘 안 가려진다.
- [ ] 상호작용 위치는 대상에서 12~13 정도로 잡는다. 정확히 15에 서면 소수점 오차로 실패할 수 있다.
- [ ] 2인용 아이템은 둘이 15 이내에 붙어 있어야 움직이므로, 운반 경로의 폭이 넉넉하다.

**연구용** (측정이 의미 있도록)
- [ ] 의도한 협력 능력 말고 다른 이유로 막히지 않는다 (길이 너무 복잡함, 단서 문장이 애매함 등).
- [ ] 효율 차이가 지표로 남는다 (클리어 step, `attempts`, `team.metrics`의 이동거리·판 지킨 시간·보너스·메시지 수).

---

## 10. 눈으로 확인하기

| 방법 | 명령 |
|---|---|
| 배치 보기 | `python -m mapgen.editor --load map_datas\s25_my_map.json` (또는 런처 맵 탭 → 선택 맵 편집·테스트) |
| 직접 풀어 보기 | 에디터에서 `P` → W 전진, A/D 회전, Space 상호작용, X 내려놓기, Tab 에이전트 바꾸기 |
| 실행 파이프라인 확인 | `python benchmark.py --policy tooluse --map-file map_datas\s25_my_map.json --steps 30` (오류 없이 끝나는지) |
| LLM 실행 | 런처 실행 탭에서 LLM 코드 정책, 최대 step = `recommended_steps` 이상 (`key.txt` 필요) |

에디터에서 저장해도 시나리오 맵의 목표 문장과 규칙은 유지됩니다. 다만 `python -m scenarios`를 다시 돌리면 `.py` 기준으로 덮어쓰므로, **고칠 때는 `.py`를 고치는 것이 기준**입니다.

---

## 11. 자주 하는 실수 (기존 12개를 만들며 실제로 겪은 것)

| 증상 | 원인 | 해결 |
|---|---|---|
| `--check`에서 `NOT CLEARED`, 레버/버튼 이벤트가 안 생김 | 대상에서 정확히 15 떨어진 곳에 섬. 대각선 이동의 소수점 오차로 15를 살짝 넘음 | 12~13 거리에 서기 |
| 에이전트가 같은 자리에서 계속 막힘 | 직선 경로가 벽이나 기둥을 지남 (`goto`는 길찾기를 안 함) | 경유점 `goto`를 하나 더 넣기 |
| `test_exported_maps_match_the_scenario_code` 실패 | 코드에 튜플 `(x, y)`를 썼는데 JSON에서는 리스트가 됨, 또는 내보내기를 안 함 | 좌표는 리스트 `[x, y]`로 쓰고 `python -m scenarios 이름` 다시 실행 |
| 실수 plan과 정답 plan의 클리어 step이 같음 | 실수가 아무 영향을 주지 않음 | 실수가 상대를 기다리게 하거나 리셋을 일으키도록 바꾸기 |
| 2인 운반 중 `move_blocked` | 두 사람의 회전/전진 step이 어긋남 | `carry_legs` + `barrier` 사용 |
| `KeyError: 'add_...'` 또는 `AttributeError: add_...` | kind 이름 오타, 또는 엔진에 없는 물체 | 3장 표의 kind 확인, 없으면 7장 |
| 런처 목록에 맵이 안 보임 | `map_datas/`에 JSON이 없음 | `python -m scenarios 이름` 실행 후 런처 "목록 새로고침" |

---

## 12. SCENARIOS.md에 붙일 설명 틀

"한눈에 보기" 표에 한 줄을 추가합니다.
```markdown
| s25_my_map | 이름 | 계열 | 2 | 클리어 조건 한 줄 | 권장 step | 정답 / 실수 후 |
```

맨 아래에 절을 추가합니다.
```markdown
## s25 이름 (계열)
- **파일**: `s25_my_map.py` (가로×세로)[, 규칙 …]
- **목표**: 클리어 조건 → `이벤트 이름`
- **의도**: 무엇을 측정하는지, 왜 혼자서는 안 되는지
- **배치**: 방 구조, 장치 위치, 누가 어디서 시작하는지
- **비밀 값**: 정답 코드/배선/주기 등 (관찰에 안 보이는 것)
- **단서와 화면**
  | 물체 | 위치 / 보는 사람 | 내용 (원문 요약) |
  |---|---|---|
  | clue_A | 방 A | … |
- **정답 흐름**: 1) … 2) … 3) …
- **실수하면**: 무엇을 잃는지 (리셋/밀려남/대기)
```
