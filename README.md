# MACI
(This repository is for the 2026 R&E project at CBSH 1st students.)


MACI is a project designed to analyze and evaluate collaboration between multiple AI agents in a shared environment.

---

## Project Overview

Most existing multi-agent evaluation methods focus mainly on whether the agents successfully complete a task or how much reward they receive.

However, a final success or failure score alone cannot explain what actually happened during the collaboration process.

For example, a failure may occur because:

* One agent provided incorrect information
* Another agent misunderstood a message
* The agents failed to coordinate their roles
* An agent made an incorrect plan
* An agent failed to detect or recover from an earlier mistake

MACI aims to identify these differences by analyzing the full interaction process between agents.

---

## GUI 실행

VS Code PowerShell 터미널에서 프로젝트 폴더로 이동한 뒤 처음 한 번 패키지를 설치합니다.

```powershell
python -m pip install -r requirements.txt
python launcher.py
```

또는 `./Start-MACI.ps1`을 실행하면 필요한 패키지를 확인한 뒤 GUI를 엽니다. 이 작업 공간에서는 준비된 Python 환경을 사용해 `.\.venv-gui\Scripts\python.exe launcher.py`로도 실행할 수 있습니다.

GUI에서 다음 순서로 실험할 수 있습니다.

1. **맵**: 기본 맵을 선택하거나 시드·에이전트 수·퍼즐 수·포탈 수를 지정해 생성합니다. 저장된 맵을 목록에서 선택하거나 경로를 입력할 수도 있습니다. 에디터에서 `P`로 테스트하고 `Ctrl+S`로 저장한 뒤 창을 닫으면 선택 맵에 반영됩니다.
2. **실행**: **일반 맵 / 압력판** 또는 **두 방 순서 퍼즐**을 선택합니다. 두 방 퍼즐은 시드·방마다 번호판 수·정답 입력 수·허용 리셋 횟수를 설정합니다. 최대 step은 퍼즐의 턴 제한이 됩니다. 일반 맵은 규칙 기반(`tooluse`)으로 먼저 동작을 확인할 수 있지만 이 정책은 번호판 퍼즐을 풀지 못합니다. 퍼즐의 LLM 실행은 **LLM 코드 정책**을 선택하고 모델·API 주소를 설정합니다. 프로젝트 루트의 `key.txt`에 API 키만 입력하세요. 환경변수는 사용하지 않습니다.
3. **결과**: 완료된 실행의 총점·단체 점수·에이전트별 내역·행동·메시지·이벤트를 확인합니다. 예전 결과도 목록에서 선택할 수 있습니다. **이동 다시 보기**로 시각적으로 재생합니다. 전체 생성 코드는 `benchmark_runs/*.jsonl`에 있습니다.
4. **LLM 채점**: 결과를 선택하고 판정 모델·최대 턴·에이전트 필터를 설정합니다. 최대 턴과 에이전트를 비우면 전체를 채점합니다. 기준 모델(`upstage/solar-pro4`)의 결과로 100점 기준을 등록할 수 있습니다. 채점 출력은 결과 파일 옆 `*.judge.log.txt`에도 저장됩니다.

진행 로그는 창 아래에 표시됩니다. 목록·결과·로그 위에서 마우스 휠로 스크롤할 수 있습니다. 입력칸에서 `Ctrl+A`로 내용을 지우고 새 값을 입력하세요. **작업 중단** 또는 창 닫기는 진행 중인 작업도 중단합니다. 부분 로그에는 완료 점수가 없을 수 있습니다. LLM 실행과 채점은 API 사용 비용이 발생할 수 있습니다.

**실행 → 디버깅: 켜짐**으로 설정하고 실행하면 **디버그** 탭에서 상세 로그를 실시간으로 봅니다. LLM 요청 시작·생성 코드·컴파일/실행 결과·복구 대기·행동·메시지·퍼즐 이벤트를 표시하며, step 완료 전의 오류 검사도 바로 나타납니다. 최신 내용을 자동으로 따라가고 휠로 과거 내용을 살펴보거나 **최신 로그로 이동**으로 돌아올 수 있습니다. GUI에는 최근 3,000개 원본 로그 행을 보관하며 전체 상세 로그는 `<실행 이름>.debug.jsonl`에 즉시 저장합니다. 터미널 실행은 `python benchmark.py --debug ...`를 사용합니다. 디버깅을 끄면 상세 로그 파일은 생성하지 않으며 기존 실행·검사 로그는 유지합니다.

LLM context는 에이전트별로 누적합니다. 이전 요청·모델 응답·코드 제출 검사 결과와 각 step의 자기 관찰·실제 행동·다음 관찰을 다음 LLM 요청에 함께 보냅니다. 다른 에이전트의 비공개 관찰이나 관찰자용 전체 맵은 포함하지 않습니다. 코드 정책은 코드를 재사용하되 다음 코드 생성/복구 요청 때 이력을 전달합니다. 에피소드마다 새 이력으로 시작하고 `CodePolicy.reset()`도 이력을 비웁니다.

Context 관리와 압축은 **행동 코드를 만드는 동일 모델의 재량**입니다. 모델은 `manage_context(summary, keep_recent_messages, inbox_recent_messages?)` 도구로 직접 작성한 요약과 보존 범위를 제출합니다. 프로그램은 요약문을 그대로 적용하며 별도 요약 모델, 자동 요약, 임의 이력 절단을 사용하지 않습니다. 기본으로 전체 이력과 inbox를 전달하며, 모델이 선택하면 과거 이력을 요약으로 교체하고 최근 메시지를 지정한 수만큼 보존합니다. 시스템 규칙·현재 관찰·진행 중인 tool 호출/응답은 항상 보존하고, 새로운 연락은 inbox 보존 설정과 관계없이 전달합니다. `--context-max-tokens 64000`은 길이 경고 기준이며 강제 압축 조건이 아닙니다. 길이는 UTF-8 바이트 기반 보수적 추정치로 표시하며 실제 모델 토큰 수와 다릅니다. 모델이 압축하지 않으면 공급자의 context 한도에 도달할 수 있습니다. Tool 호출을 지원하지 않는 공급자에서는 이 관리 도구를 사용할 수 없습니다.

원본 이력은 실행 중 `<실행 이름>.context_archive.jsonl`에 기록하고, 완료 후 `.context.json`에도 저장합니다. 실제 전송용 이력은 `.working_context.json`, 모델이 제출한 요약·보존 범위·압축 전후 길이는 `.context_compressions.jsonl`에 남깁니다. Step 로그의 `decision.context_compression`과 디버그 `context_compressed` 이벤트로 관리 상태를 확인할 수 있습니다. 설계는 모델 주도 메모리 도구를 제안한 [MemGPT](https://arxiv.org/abs/2310.08560)와 이력을 요약 상태로 이어가는 [ReSum](https://arxiv.org/abs/2509.13313)을 참고했습니다. 논문의 학습된 요약기나 강화학습 절차를 재현한 구현은 아닙니다.

행동 함수의 기본 레이아웃은 `enviroment/policy_template.py`입니다. 코드 생성 프롬프트는 관찰/메모리/물체 목록을 준비하는 부분과 `finish`, `find_object`, `move_toward`, `send_message` 헬퍼를 제공하고 LLM에게 `DECISION START/END` 영역의 판단 로직을 채우도록 안내합니다. LLM은 완성된 `decide(observation)` 전체를 제출하며 기존 컴파일·안전성·실행 검사를 통과해야 합니다. `finish`를 통해 모든 행동에 메모리를 포함하고 현재 시야 밖의 기억한 물체도 조회할 수 있습니다. `move_toward`는 직선 이동 헬퍼이므로 벽 우회나 미끼 번호판 회피를 위한 경유점은 판단 로직에서 선택해야 합니다. 초기 코드 생성과 오류 복구, LiveCodePolicy 및 HybridPolicy의 코드 모드에 같은 틀을 제공합니다.

**에이전트 이동 창**은 실행 시 자동으로 열립니다 (실행 탭에서 끌 수 있음). 맵·벽·번호판·문·이동 경로와 에이전트 위치를 표시하며 오른쪽에서 해당 step의 행동·메시지·이벤트를 볼 수 있습니다. 일시정지, 처음, 이전/다음, 최신 step, 재생 속도 버튼을 제공합니다. `Space`는 재생/정지, 좌우 방향키는 step 이동입니다. 움직임은 기록된 step 사이를 보간해 표시합니다. 관찰자용 전체 상태는 에이전트 관찰에 포함되지 않습니다. 이동 창을 닫아도 실행은 계속됩니다.

두 방 퍼즐의 번호판 번호와 전체 입력 순서는 시드 기반 난수로 부여됩니다. 같은 시드는 같은 퍼즐을 재현하며 실행 도중이나 오입력 리셋 후에도 번호·순서는 바뀌지 않습니다. 각 방의 안내판에는 자기 차례만 표시되므로 메시지로 공유 순서를 맞춰야 합니다. 번호판의 반경 10 범위에 닿으면 자동 입력되며 `press_button`은 필요하지 않습니다. 머무르면 반복 입력되지 않고 나갔다 다시 들어와야 재입력됩니다. 이동 중 다른 번호판을 스쳐도 입력되므로 번호판 줄 아래로 우회한 뒤 목표에 접근해야 합니다. 이동 창의 번호판 주변 원은 접촉 범위입니다.

LLM의 초기 설명에는 자신의 ID, 상대 에이전트 ID, 공통 환경·조작 규칙과 최소 목표를 제공합니다. 두 방 퍼즐에서는 접촉 자동 입력, 하나의 공유 순서, 방별 안내판이 자기 부분만 표시한다는 점, 턴당 한 입력, 오입력·동시 입력 시 전체 초기화, 표시판의 정보 범위와 실패 제한을 알려줍니다. 실제 정답 순서·번호 배치·이동 경로·메시지 교환 전략은 알려주지 않습니다. 안내판 내용은 시야에 들어온 물체의 관찰 데이터로 얻습니다.

GUI **실행** 탭의 **목표 알려주기** 토글로 초기 목표 설명을 켜거나 끌 수 있습니다(기본: 켜짐). 끄면 목표 문장만 숨기며 상대 ID, 조작 규칙, 순서 입력·초기화 같은 최소 규칙과 환경 내 안내판은 유지됩니다. 실제 클리어 판정과 점수는 바뀌지 않습니다. CLI에서는 `--hide-goal`을 붙이고, 실행 로그의 `reveal_goal`에서 사용한 설정을 확인할 수 있습니다.

**힌트 없는 10자리 협력**은 별도 환경입니다. `clue`와 `display`가 없으며 각 방의 5개 번호판으로 10자리를 입력합니다. A와 B가 각 5자리를 입력해야 하므로 한 에이전트만으로는 클리어할 수 없습니다. 정답과 방별 차례는 맵 배치 시드와 무관하게 암호학적 난수로 생성하며 정답·부분 정답 여부·순서 힌트를 에이전트에게 전달하지 않습니다. 10자리 전체를 제출한 뒤 판정하며, 오답이나 동시 입력이면 입력 진행도·두 에이전트의 위치·방향·행동 메모리를 초기 상태로 되돌리고 해당 입력에 참여한 에이전트에게 각각 -3점을 줍니다. context·받은 메시지·토큰 사용량·정답은 유지하고 코드 캐시를 비워 다음 턴에 새 계획을 세웁니다. 전체 턴 제한까지 재시도할 수 있으며 제한 턴을 소진하면 실패합니다. 따라서 추론으로 정답을 식별할 수 없는 통제 환경이며 우연한 정답까지 불가능하다고 주장하지 않습니다. 정답 후보는 `252 × 5^10 = 2,460,937,500`개입니다. 정확한 정답 시퀀스는 로그에도 저장하지 않으므로 배치 시드만으로 정답을 재현할 수 없습니다.

GUI에서 **로컬 모델 (8080) 사용**을 누르면 현재 서버의 Bonsai 모델과 `http://127.0.0.1:8080/v1`, **LLM 행동 / 코드** 정책을 설정합니다. 이 정책은 모델의 JSON 행동과 Python 코드 응답을 모두 받습니다. 로컬 주소에서는 `key.txt`가 필요하지 않습니다. CLI 실행 예:

```powershell
python benchmark.py --environment blind_code --policy hybrid --base-url http://127.0.0.1:8080/v1 --model models/Ternary-Bonsai-2-27B-PTQ1_0.gguf --steps 150
```

두 방 퍼즐은 서로 다른 step에 한 개씩 올바른 번호판에 진입해야 진행됩니다. 한 step의 행동은 동시 실행이므로 두 에이전트가 같은 step에 번호판을 밟거나 한 이동으로 여러 번호판을 지나가면 `simultaneous_input`으로 전체 초기화됩니다. 잘못된 순서도 `wrong_order`로 전체 초기화됩니다. 초기화된 시도의 입력으로는 문을 열 수 없으며 처음부터 전체 순서를 다시 맞춰야 합니다.

새 실행에는 초기 상태를 담은 `*.scene.json`과 매 step의 `world`·`facing`·`failure`가 저장됩니다. 이전 형식 JSONL은 에이전트 위치만 재생할 수 있습니다. 터미널에서도 실행 가능합니다.

이동 화면 오른쪽에는 현재 step의 누적 총점·팀 점수·에이전트별 점수가 표시됩니다. **소통 메시지** 탭에서는 해당 시점까지 전달된 메시지를 최신순으로 확인하며 발신자 → 수신자, step, 본문이 표시됩니다. 긴 메시지는 줄바꿈되고 마우스 휠로 이전 메시지를 볼 수 있습니다. **행동 / 점수 내역** 탭에서는 행동·오류·이벤트와 개인 점수의 획득·감점 내역을 확인합니다. 실시간 실행과 다시 보기에 모두 적용되며, 이전 step으로 돌아가면 점수와 메시지도 그 시점으로 돌아갑니다. 실시간 점수는 새 실행 로그부터 저장됩니다.

LLM 코드 정책의 실행 오류가 발생하면 새 코드가 실행에 성공할 때까지 현재 step에서 기다립니다. 기다리는 동안 이동·회전하거나 추가 step을 소비하지 않습니다. 코드 재생성 또는 재실행이 실패하면 잠시 대기 후 재시도하며, 성공한 행동으로 현재 step을 이어갑니다. 복구 대기는 일반 정체 재계획 횟수 제한과 별개로 진행됩니다. GUI 로그에 `[CODE RECOVERY]`가 표시되며 **작업 중단**으로 대기를 끝낼 수 있습니다. 복구 결과는 `decision.recovery`에 기록됩니다.

에이전트가 제출한 코드는 `py_compile`로 검사하며 실행 직전에도 다시 검사합니다. 컴파일 성공은 문법 검사 통과를 뜻하고, 실제 실행 성공 여부는 샌드박스에서 별도로 확인합니다. 에이전트마다 `compile_attempts/successes/failures`와 `execution_attempts/successes/failures`를 누적합니다. 제출 단계와 실행 직전의 검사는 각각 1회로 세며 동일 코드의 재검사도 포함합니다. 컴파일 실패 시 실행 횟수는 증가하지 않습니다. 각 검사 결과·에이전트·코드 SHA-256·누적 횟수는 `*.code_checks.jsonl`에 즉시 저장되므로 복구 대기 중 중단해도 남습니다. step 로그의 `decision.code_checks`와 완료 점수 파일의 `code_checks`에도 누적 횟수가 기록되며 결과·이동 화면에서 볼 수 있습니다.

```powershell
python benchmark.py --environment sequence_rooms --sequence-seed 42 --steps 80
python viewer.py benchmark_runs\실행결과.jsonl
```

기본 시야 거리는 200 월드 단위이며 시야각은 90도입니다. 벽에 의한 시야 차단은 유지됩니다. 생성 코드의 사용 턴 수 제한은 없으며 CodePolicy와 HybridPolicy는 같은 코드를 계속 재사용할 수 있습니다. 기존 정체 감지·재계획·실행 오류 복구는 유지됩니다. 로그의 `decision.code_turns`와 이동 화면의 **행동 / 점수 내역** 탭에서 현재 코드의 사용 턴 수를 확인할 수 있습니다.

생성 코드가 상태 재확인 간격을 정합니다. 기본 함수 틀의 판단 영역에서 `recheck_after = 3`처럼 양의 정수를 지정하면 `finish()`가 행동에 포함합니다(기본값: 5). 첫 실행이 step 1이면 step 4의 행동 전에 LLM에 최신 관찰과 누적 context를 보내 현재 실행 상태를 다시 판단시킵니다. CodePolicy와 HybridPolicy의 캐시된 코드에 적용되며 매 턴 같은 값을 반환해도 예정 시점은 뒤로 밀리지 않습니다. 재확인 후 같은 코드를 유지할 수도 있습니다. 기존 코드가 이 필드를 반환하지 않으면 정기 재확인은 예약되지 않습니다. 로그의 `decision.next_review_step`과 **행동 / 점수 내역** 탭에 다음 재확인 step을 표시합니다.

새 연락이 관찰의 `inbox`에 들어오면 그 턴의 캐시 실행 전에 LLM을 호출합니다. 정기 재확인 예약과 일반 재계획 횟수 제한보다 우선하며, 텍스트·질문·명령·belief 등 모든 메시지 유형에 적용됩니다. 한 관찰에 도착한 여러 메시지는 한 번에 전달하고 이미 확인한 메시지는 호출을 반복하지 않습니다. 동시 실행 중 행동 적용 단계에서 보낸 메시지는 다음 턴 시작 관찰에 들어오며, 수신 에이전트는 그 턴에 바로 LLM으로 판단합니다. 현재 코드가 오류 없이 실행 중이면 LLM은 `keep_current_code`로 코드를 그대로 두거나 `submit_policy_code`로 새 코드를 낼 수 있습니다. 그대로 둔 경우 `decision.replan.kept`가 `true`입니다. `decision.message_interrupt`와 디버그 로그에서 연락에 의한 호출을 확인할 수 있습니다.

힌트 없는 협력 환경은 `clue`와 `display/update` 블록 및 부분 정답 피드백이 없음을 목표 토글과 관계없이 에이전트에게 알립니다. 공통 설명에는 과도한 출력 토큰 소비가 감점된다는 점도 명시합니다. 기준은 에이전트별·에피소드별 출력 API 토큰 50,000개까지 감점 없음, 초과 출력분 1,000개당 1점 비례 감점입니다. 입력 및 반복 전송한 누적 context는 기록만 하고 감점하지 않습니다. 재시도에서 생성한 출력도 포함됩니다. 실제 감점은 개인 점수와 총점에 반영되며 `token_usage`, `token_penalty`로 저장됩니다. API가 사용량을 보고하지 않은 요청은 `unreported_requests`로 따로 표시하고 토큰 수를 추정해 감점하지 않습니다. 이전 실행은 토큰 사용량을 기록하지 않았으므로 소급 감점하지 않습니다.

## 사람이 플레이하기 (2인, 한 컴퓨터)

**실행** 탭의 **사람이 플레이 (2인)** 버튼을 누르거나 `python play.py --map-file map_datas/s01_deadlock.json --steps 300`처럼 실행합니다. 환경과 맵 설정은 LLM 실행과 같습니다.

- 두 사람이 A와 B를 맡아 턴제로 번갈아 조종합니다. 매 step 두 사람이 행동을 하나씩 고르면 동시에 적용됩니다.
- 상대 차례에는 화면이 가려져서 정보 비대칭이 유지됩니다.
- 화면에는 LLM이 받는 관찰과 같은 정보만 나옵니다.
  - 자기 시야의 물체와, 예전에 본 물체(흐리게 표시)
  - 근처 벽, 받은 메시지
  - 직전 행동 결과와 알림, 현재 단계
  - 과제 설명(H 키)
- 결과는 `benchmark_runs/human_*.jsonl`과 `.score.json`에 같은 형식으로 저장됩니다. 그래서 이동 창, 채점, 사람 채점, 집계에 그대로 쓸 수 있고 LLM 결과와 직접 비교할 수 있습니다.

**조작**

| 키 | 동작 |
|---|---|
| ←/→ | 15도 회전 (Shift: 45도) |
| ↑ | 20 전진 (Shift: 5) |
| Space | 대기 |
| E | 손 닿는 물체와 상호작용: 줍기, 버튼, 레버, 열쇠 |
| D | 내려놓기 |
| R / F | 각도 / 거리 입력 |
| T | 메시지 입력 |
| 우클릭 | 그 지점 쪽으로 회전 |
| 좌클릭 | 물체 자세히 보기 (턴 소모 없음) |

창을 닫으면 그 시점에서 미완료로 기록됩니다.

## 실행 로그 보기 (원격 / 로컬)

`python pi_logs.py`로 실행 로그를 봅니다.
- **원격:** 라즈베리파이 같은 원격 컴퓨터의 로그입니다. 기본 주소는 `jikun@100.105.194.90`, 기본 폴더는 `~/MACI/benchmark_runs`이며 `--host`와 `--remote-dir`로 바꿀 수 있습니다.
- **로컬:** 이 컴퓨터의 로그입니다. `python pi_logs.py --local`로 열거나 창 위쪽의 **원본** 버튼으로 바꿉니다. 기본 폴더는 이 프로젝트의 `benchmark_runs`이고, `--local <폴더>`로 다른 폴더를 볼 수 있습니다. 내려받기 없이 파일을 바로 열고, 진행 중인 실행도 그 파일을 바로 실시간으로 따라봅니다.

아래는 원격 모드 기준 설명입니다(목록, 상세, 다시 보기, 실시간 따라보기는 로컬도 같음).

- **연결:** SSH 키 로그인으로 원격 실행(하위 폴더 포함)을 찾습니다. 원격에는 python3만 있으면 되고 따로 설치할 것은 없습니다.
- **목록:** 진행 중 / 클리어 / 실패 / 중단 / 멈춤 상태를 보여 줍니다. 20초마다 자동으로 새로고침됩니다.
- **선택한 실행:** 모델, step, 총점, 중단 사유와 콘솔 로그 끝부분을 보여 줍니다.
- **가져오기:** 실행 파일을 `benchmark_runs/pi/<원격 경로>`로 내려받습니다. 대화 이력 파일은 크기 때문에 선택 사항입니다.
- **이동 다시 보기:** 내려받은 뒤 이동 창으로 엽니다.
- **실시간 따라보기:** 진행 중인 실행의 새 step만 3초마다 이어 받아 이동 창에 보여 줍니다. 실행이 끝나면 점수 파일까지 받고 자동으로 멈춥니다.

## 최종 벤치마크 프로토콜

**조건.** `--controller decentralized`(기본)는 에이전트마다 같은 모델의 LLM이 하나씩 붙어 메시지로 협력합니다. `--controller central`은 LLM 하나가 모든 에이전트의 관찰을 동시에 받아 `decide()` 코드 하나로 전원을 조종합니다. 관찰에는 `agent_id`와 나머지 에이전트의 같은 step 관찰(`team`)이 추가됩니다. 정보가 처음부터 공유되므로 소통이 필요 없는 상한선 조건이며, 두 조건의 차이가 분산 협력의 소통 비용입니다. 중앙 조건의 토큰 허용량은 조종하는 에이전트 수만큼 늘어나고 감점은 똑같이 나눕니다. GUI **실행** 탭의 **조종** 버튼으로도 바꿀 수 있습니다.

**반복 실험.** `experiment.py`는 모델 × 조건 × 시드를 같은 설정으로 실행합니다. 기본 프로토콜은 두 방 순서 퍼즐 축소판(방마다 번호판 3개, 입력 2회, 80 step)입니다. 결과는 `benchmark_runs/experiments/<이름>/`에 저장되고, 같은 이름으로 다시 실행하면 끝난 실행을 건너뜁니다. 설정이 다르면 섞이지 않도록 거부합니다. 집계(`summary.json`/`summary.csv`)는 로그에서 바로 계산한 지표만 씁니다: 성공률(Wilson 95% 신뢰구간), 클리어 step, 리셋 원인, 잘못된 행동, 코드 오류, 메시지 수, 토큰(캐시 적중 포함). 같은 시드끼리 두 조건을 짝지어 정확 McNemar 검정으로 비교합니다.

```powershell
python experiment.py --name pilot --models openai/gpt-6-luna --seeds 1-8
python experiment.py --name pilot --summarize
python experiment.py --name smoke --policy tooluse --controllers decentralized --seeds 1-2   # API 없이 점검
```

**잘못된 실행의 감점과 피드백.** 관찰의 `last_action_result`가 직전 행동이 `ok`/`invalid`/`no_effect` 중 무엇이었는지와 이유를 알려줍니다. `notices`는 리셋 같은 최근 알림을 원인 제공 여부(`caused_by_you`)와 함께 전달합니다. 알 수 없는 행동 종류와 없는 수신자에게 보낸 메시지도 이제 조용히 무시하지 않고 invalid로 처리합니다. 감점은 모두 개인 점수에 들어가며 종류별 하한이 있습니다.

| 잘못된 실행 | 감점 | 하한 |
|---|---|---|
| invalid action | -1 | -10 |
| 코드 제출 거부·실행 오류 | -1 | -15 |
| 효과 없는 상호작용 | -0.5 | -10 |
| 틀린/동시 입력 리셋 | -3 | 없음 |

감점 안내는 에이전트 설명에 자동으로 붙습니다.

**점수 가중치.** 가중치는 `scoring_weights.json`에서 읽습니다(`--score-config`로 다른 파일 지정 가능). 사용한 값은 `*.score.json`의 `score_config`에 저장됩니다. 기본값은 협력 중심입니다.
- 목격 점수: 0.2점(안내판 1점)으로 낮췄습니다.
- 순서 입력: 3점입니다.
- 순서 이어받기: 상대의 올바른 입력 바로 다음 차례를 맞게 입력하면 2점을 추가로 받습니다.
- 클리어: 60점, 시간 보너스는 최대 20점입니다.

**판정기 다변화와 사람 채점.** `maci_judge.py --judge-model a,b`처럼 판정 모델을 여러 개 지정할 수 있습니다. 턴별 점수는 `*.judges.json`에 저장되고, 100점 기준도 판정 모델별로 따로 저장됩니다. GUI **사람 채점** 탭은 판정 모델과 같은 턴 정보와 기준으로 0~10점을 입력받아 `*.human.<채점자>.json`에 저장합니다. 사람이 판정 점수에 영향받지 않도록 판정 점수는 일치도 계산 결과에만 표시됩니다. **일치도 계산** 또는 `python judge_agreement.py <결과.jsonl>`은 판정 모델끼리, 그리고 판정 모델과 사람 사이의 일치도를 공통 턴에서 계산합니다. 지표는 Pearson r, Spearman ρ, QWK, MAE, 1점 이내 비율입니다.


### 시나리오 맵 (협력 실험 12종)

`map_datas/s01_deadlock.json` ~ `s12_unreliable_eyes.json`은 협력 능력별(순서 계획, 공동 추론, 통신 규약, 사회적 딜레마, 작업 분배, 시간 예측, 신뢰 검증) 고난도 맵입니다. 런처의 **맵** 탭 목록에서 고르고 **실행** 탭에서 최대 step을 맵별 권장값(120~200) 이상으로 두고 실행합니다. 실패 상태는 없고 실수하면 시간만 잃습니다. 맵별 목표·의도·단서 내용은 [scenarios/SCENARIOS.md](scenarios/SCENARIOS.md), 이번 추가에 따른 변경 사항은 [TEAM_CHANGES.md](TEAM_CHANGES.md)에 있습니다.

```powershell
python benchmark.py --map-file map_datas\s05_lossy_sync.json --steps 150
python -m scenarios --check     # 맵 12개가 실제로 풀리는지 검증 후 map_datas/에 다시 내보내기
```

---

## Core Objective

The main research question of MACI is:

> Which agent caused the failure, at what point did the failure become decisive, and which message or action had the greatest influence?

MACI records the complete interaction trace of each episode, including:

* Agent observations
* Messages exchanged between agents
* Selected actions
* Changes in the environment
* Task progress
* Rewards and milestones

This allows the system to analyze not only the final result, but also the process that led to it.

---

## Failure Analysis

When a collaboration failure occurs, MACI attempts to identify:

* The agent responsible for the failure
* The decisive interaction step
* The message or action that influenced the outcome
* Whether the failure could have been detected or recovered from

Failures may be classified into categories such as:

* Perception
* Belief Tracking
* Communication
* Planning
* Coordination
* Execution
* Verification
* Evaluation

---

## Counterfactual Replay

MACI uses counterfactual replay to verify whether a specific message or action actually caused a failure.

The system can replay the same situation after changing one part of the original interaction, such as:

* Removing a message
* Correcting incorrect information
* Replacing an agent's action
* Changing the order of messages
* Delaying or blocking communication
* Swapping agent roles

The results of the original execution and the modified execution are then compared.

This makes it possible to explain failures using reproducible evidence rather than relying only on assumptions or generated explanations.

---

## Project Goal

The final goal of MACI is to build an evaluation framework that can measure and explain multi-agent collaboration.

Rather than asking only:

> Did the agents succeed?

MACI focuses on a more detailed question:

> How did the agents collaborate, where did the collaboration fail, and why did that failure occur?

---

## Continuous movement

Agent positions and headings use floating-point world coordinates. Screen pixels
are only a rendering detail; fractional distances and angles do not get rounded
by the simulation. To move 2.5 units in the current facing direction, return:

```python
{"type": "move_forward", "distance": 2.5}
```

Use `{"type": "turn", "angle": 37.5}` to rotate the body 37.5 degrees clockwise
in place, then move forward on the next step. Negative angles rotate
counterclockwise. Facing is in degrees: 0 points right, 90 down, 180 left, and
270 up. Forward motion preserves facing; rotation changes both heading and the
view cone without changing position. `turn(facing=...)` remains available for
absolute orientation; provide exactly one of `angle` or `facing`.

`move(dx, dy)` is removed and rejected as an invalid action, including commands
from another agent. Agents cannot strafe or walk backward. To move toward a
target, first rotate by `(target_facing - facing + 180) % 360 - 180`, then advance.

The observation's `self` includes `x`, `y`, `facing`, a unit `heading` vector,
`max_move` (default 20; `None` means unlimited), and `last_move`:

```python
{
    "step": 1,
    "requested_distance": 2.5,
    "distance": 2.5,
    "dx": 2.5,
    "dy": 0.0,
    "blocked": False,
    "limited": False,
}
```

`last_move` is initially `None` and persists until the next movement action.
Its distance and displacement exclude portal teleportation. `blocked` means
collision, a map boundary, or missing cooperative helpers shortened the capped
move; `limited` means the request exceeded `max_move`. Walls and locked doors
stop movement just before contact, including obstacles crossed mid-move.
The same spatial state is saved under each agent's `spatial_state` in the run log.
Movement still advances once per simulation step; distances are not velocities
and this interface does not introduce elapsed-time physics or rendering animation.

The pygame map editor has no visible grid or placement snapping. Dragging and
placing entities keeps fractional world coordinates. In test play, hold W/Up
to advance 2.5 units per action; A/Left/Q and D/Right/E rotate the body by 15
degrees per action. Hold Shift for 0.25-unit forward steps and 1.5-degree turns.
S/Down does not move backward. The mouse wheel rotates agents in edit mode with
the same angular increments. The sidebar shows position, facing, and heading.

Run the movement regression checks without external API calls:

```sh
python3 -m unittest discover -s tests -v
```

---

## Five-level learning environment

LLM runs require a submitted Python `decide(observation)` policy. Direct JSON
actions are rejected at code submission. The GUI offers **LLM 코드 필수 / 재사용**;
the local-model button also selects this mode. Old `--policy hybrid` commands
now use `CodePolicy` as a compatibility alias, so they cannot bypass code execution.
Generated code is compiled, validated and executed in the existing sandbox,
then cached across steps. Initial generation receives the current observation.
The code's `recheck_after` schedules LLM review; incoming messages still force
immediate review, and level changes/retries invalidate old plans. Intentional
waiting and communication do not trigger the stationary-agent stall heuristic;
blocked forward movement still does. No code-reuse turn cap is imposed.

Select **5단계 학습 퍼즐** in the pygame launcher's run tab. The default
150-step budget becomes 600 when selecting this mode; an edited budget is kept.
Or run:

```powershell
python benchmark.py --environment curriculum --sequence-seed 42 --steps 600
```

The levels progress from one pad, to a two-pad sequence in A's room, to a
two-room sequence, a six-input sequence, and finally a ten-input sequence with
repeated digits. Levels 3–5 require both agents. Pad numbers and target order
vary by seed. There are no clue/display blocks or answer hints. Each agent
receives its own input result and accepted position through `input_feedback`;
the next correct digit is never exposed. Agents can learn by trying inputs
and exchanging observations. `level_state` reports level, length, completed
levels and resets; it does not report the global current input position.

A correct level advances automatically. Wrong or simultaneous inputs reset
the current attempt and positions and penalize participating agents by 3 points.
The same sequence remains on retry. Conversation, messages, action memory and
token accounting persist through retries and transitions, while cached action
code is invalidated so the LLM can revise its plan. Completion gives each
contributing agent 10 points per level; only level 5 opens the final vault.
The episode turn budget covers all five levels. The viewer displays current
level and completed count; run logs and score files retain level state/events.
By default agents cannot see numeric scores. Add `--show-reward` to include
their own individual score, team score, and total score in each observation's
`reward` field. This does not change the puzzle, correctness feedback, or scoring.
Compare a matched pair with `python compare_reward_runs.py visible.jsonl hidden.jsonl --out comparison.json`.
This is a MACI progression mode inspired by interactive level learning, not
an implementation of the official ARC-AGI-3 benchmark.

## Repository Access

The following members are authorized to access and modify this repository:

* Jihoon Park
* Yeomyeong Lee
* Henry Kim
* Hanwook Choi
