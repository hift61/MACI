# 에이전트가 읽는 글 (자동 생성: python -m scenarios --texts)

맵마다 에이전트에게 전달되는 글입니다. 모든 맵에 같은 공통 설명(시야, 이동, 메시지, 토큰, 감점)과 시스템 프롬프트의 물체 역할 설명은 빼고, 맵마다 다른 부분만 모았습니다. 원칙은 `scenarios/common.py`의 make_spec 주석과 MAP_HOWTO.md 6장을 따릅니다. 마지막 열은 같은 맵의 힌트 없는 버전(map_datas/<이름>_nohint.json)에서 그 단서가 어떻게 보이는지입니다(규칙 문장을 지우고 퍼즐 자료만 남김, 남는 것이 없으면 단서 자체가 없음).

## s01_deadlock (교착 상태)

- **과제 설명의 맵별 부분**: Goal: clear every stage in order (the current stage's goal is observation 'stage'). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

**1단계 'one-way door'** - 단계 안내: Both of you stand inside yard_1 at the same time.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `yard_1` | goal_zone 이름표 | courtyard | (같음) |
| `clue_A1` | clue | {"hint": "A plate can hold open a door that cannot be seen from the plate."} | (없음) |
| `clue_B1` | clue | {"hint": "This door opens only while a plate somewhere else is occupied."} | (없음) |

**2단계 'symmetric deadlock'** - 단계 안내: Both of you stand inside yard_2 at the same time.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `yard_2` | goal_zone 이름표 | courtyard | (같음) |
| `clue_A2` | clue | {"plates": "The plate in a room holds open the door of the OTHER room, not its own.", "levers": "A latch lever can open a door for good."} | (없음) |
| `clue_B2` | clue | {"plates": "The plate in a room holds open the door of the OTHER room, not its own.", "levers": "A latch lever can open a door for good."} | (없음) |

**3단계 'hard deadlock'** - 단계 안내: Both of you stand inside yard_3 at the same time.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `yard_3` | goal_zone 이름표 | courtyard | (같음) |
| `clue_A3` | clue | {"plates": "The plate in a room holds open the door of the OTHER room, not its own.", "levers": "Each locked door also has a latch lever that opens it for good."} | (없음) |
| `clue_B3` | clue | {"plates": "The plate in a room holds open the door of the OTHER room, not its own.", "levers": "Each locked door also has a latch lever that opens it for good."} | (없음) |

## s02_leapfrog (징검다리 교대)

- **과제 설명의 맵별 부분**: Goal: clear every stage in order (the current stage's goal is observation 'stage'). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

**1단계 '2 doors'** - 단계 안내: Both of you stand inside exit_1 at the same time.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `exit_1` | goal_zone 이름표 | exit hall | (같음) |
| `manual_1` | clue | {"doors": "Each door here can be held open by either of two plates, one on each side of it.", "catch": "No plate is close enough to its door to stand on it and walk through at the same time."} | (없음) |

**2단계 '5 doors'** - 단계 안내: Both of you stand inside exit_2 at the same time.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `exit_2` | goal_zone 이름표 | exit hall | (같음) |
| `manual_2` | clue | {"doors": "Each door here can be held open by either of two plates, one on each side of it.", "catch": "No plate is close enough to its door to stand on it and walk through at the same time."} | (없음) |

**3단계 '7 doors'** - 단계 안내: Both of you stand inside exit_3 at the same time.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `exit_3` | goal_zone 이름표 | exit hall | (같음) |
| `manual_3` | clue | {"doors": "Each door here can be held open by either of two plates, one on each side of it.", "catch": "No plate is close enough to its door to stand on it and walk through at the same time."} | (없음) |

## s03_split_experiment (나눠 보는 실험)

- **과제 설명의 맵별 부분**: Goal: be inside goal_zone 'exit' at the same time (everyone named in its 'agents' field, or all agents). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `wiring_note_A` | clue | {"wiring": "The levers L1-L6 are secretly wired to the gates G1-G4. Pulling a lever flips every gate it is wired to (open <-> closed).", "rule": "A gate is open exactly when an odd number of the levers wired to it are on."} | (없음) |
| `wiring_note_B` | clue | {"wiring": "The levers L1-L6 are secretly wired to the gates G1-G4. Pulling a lever flips every gate it is wired to (open <-> closed).", "rule": "A gate is open exactly when an odd number of the levers wired to it are on."} | (없음) |
| `exit` | goal_zone 이름표 | exit hall | (같음) |

## s04_half_mastermind (반쪽 마스터마인드)

- **과제 설명의 맵별 부분**: Goal: clear every stage in order (the current stage's goal is observation 'stage'). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

**1단계 '3 of 4 colours'** - 단계 안내: Open color_panel_1.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `color_panel_1` | keypad 이름표 | 3-colour code panel | (같음) |
| `btn1_red` | keypad_button 이름표 | red | (같음) |
| `btn1_green` | keypad_button 이름표 | green | (같음) |
| `btn1_blue` | keypad_button 이름표 | blue | (같음) |
| `btn1_yellow` | keypad_button 이름표 | yellow | (같음) |
| `result_screen_1` | display | {"attempt": 0, "exact": null, "misplaced": null} | (같음) |
| `panel_manual_1` | clue | {"panel": "color_panel_1 opens when its colour buttons are pressed in the right order: 3 different colours out of red, green, blue, yellow, none repeated.", "checking": "After every 3 presses the code is checked and the panel clears itself. The result is shown on the screen that belongs to the panel."} | (없음) |
| `screen_manual_1` | clue | {"screen": "This screen shows the result of the latest full code: 'exact' = right colour in the right slot, 'misplaced' = right colour in the wrong slot. It never shows which colours were entered."} | (없음) |

**2단계 '4 of 5 colours'** - 단계 안내: Open color_panel_2.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `color_panel_2` | keypad 이름표 | 4-colour code panel | (같음) |
| `btn2_red` | keypad_button 이름표 | red | (같음) |
| `btn2_green` | keypad_button 이름표 | green | (같음) |
| `btn2_blue` | keypad_button 이름표 | blue | (같음) |
| `btn2_yellow` | keypad_button 이름표 | yellow | (같음) |
| `btn2_purple` | keypad_button 이름표 | purple | (같음) |
| `result_screen_2` | display | {"attempt": 0, "exact": null, "misplaced": null} | (같음) |
| `panel_manual_2` | clue | {"panel": "color_panel_2 opens when its colour buttons are pressed in the right order: 4 different colours out of red, green, blue, yellow, purple, none repeated.", "checking": "After every 4 presses the code is checked and the panel clears itself. The result is shown on the screen that belongs to the panel."} | (없음) |
| `screen_manual_2` | clue | {"screen": "This screen shows the result of the latest full code: 'exact' = right colour in the right slot, 'misplaced' = right colour in the wrong slot. It never shows which colours were entered."} | (없음) |

**3단계 '5 of 6 colours'** - 단계 안내: Open color_panel_3.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `color_panel_3` | keypad 이름표 | 5-colour code panel | (같음) |
| `btn3_red` | keypad_button 이름표 | red | (같음) |
| `btn3_green` | keypad_button 이름표 | green | (같음) |
| `btn3_blue` | keypad_button 이름표 | blue | (같음) |
| `btn3_yellow` | keypad_button 이름표 | yellow | (같음) |
| `btn3_purple` | keypad_button 이름표 | purple | (같음) |
| `btn3_orange` | keypad_button 이름표 | orange | (같음) |
| `result_screen_3` | display | {"attempt": 0, "exact": null, "misplaced": null} | (같음) |
| `panel_manual_3` | clue | {"panel": "color_panel_3 opens when its colour buttons are pressed in the right order: 5 different colours out of red, green, blue, yellow, purple, orange, none repeated.", "checking": "After every 5 presses the code is checked and the panel clears itself. The result is shown on the screen that belongs to the panel."} | (없음) |
| `screen_manual_3` | clue | {"screen": "This screen shows the result of the latest full code: 'exact' = right colour in the right slot, 'misplaced' = right colour in the wrong slot. It never shows which colours were entered."} | (없음) |

## s05_lossy_sync (확인의 문제)

- **과제 설명의 맵별 부분**: Goal: succeed with the sync pads of group 'sync'. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.
- **맵 규칙**: `{"message_loss": 0.35, "message_delay": [0, 2], "seed": 11}`

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `manual_A` | clue | {"pads": "pad_A and pad_B must be entered in the SAME step. Entering means moving onto a pad from outside its radius.", "failure": "If only one pad is entered, whoever stands on a pad is pushed back and both pads ignore entries for a few steps.", "clock": "Every observation contains the shared step number (self.step)."} | (없음) |
| `manual_B` | clue | {"pads": "pad_A and pad_B must be entered in the SAME step. Entering means moving onto a pad from outside its radius.", "failure": "If only one pad is entered, whoever stands on a pad is pushed back and both pads ignore entries for a few steps.", "clock": "Every observation contains the shared step number (self.step)."} | (없음) |

## s06_short_radio (짧은 무전)

- **과제 설명의 맵별 부분**: Goal: clear every stage in order (the current stage's goal is observation 'stage'). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.
- **맵 규칙**: `{"message_max_chars": 10, "message_interval": 5}`

**1단계 '2-button codes'** - 단계 안내: Open panel_A1 and panel_B1.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `panel_A1` | keypad 이름표 | 4x4 panel | (같음) |
| `A1_r1c1` | keypad_button 이름표 | r1c1 | (같음) |
| `A1_r1c2` | keypad_button 이름표 | r1c2 | (같음) |
| `A1_r1c3` | keypad_button 이름표 | r1c3 | (같음) |
| `A1_r1c4` | keypad_button 이름표 | r1c4 | (같음) |
| `A1_r2c1` | keypad_button 이름표 | r2c1 | (같음) |
| `A1_r2c2` | keypad_button 이름표 | r2c2 | (같음) |
| `A1_r2c3` | keypad_button 이름표 | r2c3 | (같음) |
| `A1_r2c4` | keypad_button 이름표 | r2c4 | (같음) |
| `A1_r3c1` | keypad_button 이름표 | r3c1 | (같음) |
| `A1_r3c2` | keypad_button 이름표 | r3c2 | (같음) |
| `A1_r3c3` | keypad_button 이름표 | r3c3 | (같음) |
| `A1_r3c4` | keypad_button 이름표 | r3c4 | (같음) |
| `A1_r4c1` | keypad_button 이름표 | r4c1 | (같음) |
| `A1_r4c2` | keypad_button 이름표 | r4c2 | (같음) |
| `A1_r4c3` | keypad_button 이름표 | r4c3 | (같음) |
| `A1_r4c4` | keypad_button 이름표 | r4c4 | (같음) |
| `clue_A1` | clue | {"about": "This code opens panel_B1.", "code": "Press these 2 buttons of panel_B1 in order: the second row from the top, the first column from the left; then the bottom row, the third column from the left.", "panel": "Panel buttons are labelled r<row>c<column> (r1 = top row, c1 = left column).", "radio": "Messages here are limited to 10 characters and one message every 5 steps."} | {"code": "Press these 2 buttons of panel_B1 in order: the second row from the top, the first column from the left; then the bottom row, the third column from the left."} |
| `panel_B1` | keypad 이름표 | 4x4 panel | (같음) |
| `B1_r1c1` | keypad_button 이름표 | r1c1 | (같음) |
| `B1_r1c2` | keypad_button 이름표 | r1c2 | (같음) |
| `B1_r1c3` | keypad_button 이름표 | r1c3 | (같음) |
| `B1_r1c4` | keypad_button 이름표 | r1c4 | (같음) |
| `B1_r2c1` | keypad_button 이름표 | r2c1 | (같음) |
| `B1_r2c2` | keypad_button 이름표 | r2c2 | (같음) |
| `B1_r2c3` | keypad_button 이름표 | r2c3 | (같음) |
| `B1_r2c4` | keypad_button 이름표 | r2c4 | (같음) |
| `B1_r3c1` | keypad_button 이름표 | r3c1 | (같음) |
| `B1_r3c2` | keypad_button 이름표 | r3c2 | (같음) |
| `B1_r3c3` | keypad_button 이름표 | r3c3 | (같음) |
| `B1_r3c4` | keypad_button 이름표 | r3c4 | (같음) |
| `B1_r4c1` | keypad_button 이름표 | r4c1 | (같음) |
| `B1_r4c2` | keypad_button 이름표 | r4c2 | (같음) |
| `B1_r4c3` | keypad_button 이름표 | r4c3 | (같음) |
| `B1_r4c4` | keypad_button 이름표 | r4c4 | (같음) |
| `clue_B1` | clue | {"about": "This code opens panel_A1.", "code": "Press these 2 buttons of panel_A1 in order: the third row from the top, the second column from the left; then the top row, the last column on the right.", "panel": "Panel buttons are labelled r<row>c<column> (r1 = top row, c1 = left column).", "radio": "Messages here are limited to 10 characters and one message every 5 steps."} | {"code": "Press these 2 buttons of panel_A1 in order: the third row from the top, the second column from the left; then the top row, the last column on the right."} |

**2단계 '4-button codes'** - 단계 안내: Open panel_A2 and panel_B2.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `panel_A2` | keypad 이름표 | 4x4 panel | (같음) |
| `A2_r1c1` | keypad_button 이름표 | r1c1 | (같음) |
| `A2_r1c2` | keypad_button 이름표 | r1c2 | (같음) |
| `A2_r1c3` | keypad_button 이름표 | r1c3 | (같음) |
| `A2_r1c4` | keypad_button 이름표 | r1c4 | (같음) |
| `A2_r2c1` | keypad_button 이름표 | r2c1 | (같음) |
| `A2_r2c2` | keypad_button 이름표 | r2c2 | (같음) |
| `A2_r2c3` | keypad_button 이름표 | r2c3 | (같음) |
| `A2_r2c4` | keypad_button 이름표 | r2c4 | (같음) |
| `A2_r3c1` | keypad_button 이름표 | r3c1 | (같음) |
| `A2_r3c2` | keypad_button 이름표 | r3c2 | (같음) |
| `A2_r3c3` | keypad_button 이름표 | r3c3 | (같음) |
| `A2_r3c4` | keypad_button 이름표 | r3c4 | (같음) |
| `A2_r4c1` | keypad_button 이름표 | r4c1 | (같음) |
| `A2_r4c2` | keypad_button 이름표 | r4c2 | (같음) |
| `A2_r4c3` | keypad_button 이름표 | r4c3 | (같음) |
| `A2_r4c4` | keypad_button 이름표 | r4c4 | (같음) |
| `clue_A2` | clue | {"about": "This code opens panel_B2.", "code": "Press these 4 buttons of panel_B2 in order: the bottom row, the first column from the left; then the second row from the top, the second column from the left; then the third row from the top, the last column on the right; then the top row, the third column from the left.", "panel": "Panel buttons are labelled r<row>c<column> (r1 = top row, c1 = left column).", "radio": "Messages here are limited to 10 characters and one message every 5 steps."} | {"code": "Press these 4 buttons of panel_B2 in order: the bottom row, the first column from the left; then the second row from the top, the second column from the left; then the third row from the top, the last column on the right; then the top row, the third column from the left."} |
| `panel_B2` | keypad 이름표 | 4x4 panel | (같음) |
| `B2_r1c1` | keypad_button 이름표 | r1c1 | (같음) |
| `B2_r1c2` | keypad_button 이름표 | r1c2 | (같음) |
| `B2_r1c3` | keypad_button 이름표 | r1c3 | (같음) |
| `B2_r1c4` | keypad_button 이름표 | r1c4 | (같음) |
| `B2_r2c1` | keypad_button 이름표 | r2c1 | (같음) |
| `B2_r2c2` | keypad_button 이름표 | r2c2 | (같음) |
| `B2_r2c3` | keypad_button 이름표 | r2c3 | (같음) |
| `B2_r2c4` | keypad_button 이름표 | r2c4 | (같음) |
| `B2_r3c1` | keypad_button 이름표 | r3c1 | (같음) |
| `B2_r3c2` | keypad_button 이름표 | r3c2 | (같음) |
| `B2_r3c3` | keypad_button 이름표 | r3c3 | (같음) |
| `B2_r3c4` | keypad_button 이름표 | r3c4 | (같음) |
| `B2_r4c1` | keypad_button 이름표 | r4c1 | (같음) |
| `B2_r4c2` | keypad_button 이름표 | r4c2 | (같음) |
| `B2_r4c3` | keypad_button 이름표 | r4c3 | (같음) |
| `B2_r4c4` | keypad_button 이름표 | r4c4 | (같음) |
| `clue_B2` | clue | {"about": "This code opens panel_A2.", "code": "Press these 4 buttons of panel_A2 in order: the top row, the second column from the left; then the bottom row, the last column on the right; then the second row from the top, the first column from the left; then the third row from the top, the third column from the left.", "panel": "Panel buttons are labelled r<row>c<column> (r1 = top row, c1 = left column).", "radio": "Messages here are limited to 10 characters and one message every 5 steps."} | {"code": "Press these 4 buttons of panel_A2 in order: the top row, the second column from the left; then the bottom row, the last column on the right; then the second row from the top, the first column from the left; then the third row from the top, the third column from the left."} |

**3단계 '6-button codes'** - 단계 안내: Open panel_A3 and panel_B3.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `panel_A3` | keypad 이름표 | 4x4 panel | (같음) |
| `A3_r1c1` | keypad_button 이름표 | r1c1 | (같음) |
| `A3_r1c2` | keypad_button 이름표 | r1c2 | (같음) |
| `A3_r1c3` | keypad_button 이름표 | r1c3 | (같음) |
| `A3_r1c4` | keypad_button 이름표 | r1c4 | (같음) |
| `A3_r2c1` | keypad_button 이름표 | r2c1 | (같음) |
| `A3_r2c2` | keypad_button 이름표 | r2c2 | (같음) |
| `A3_r2c3` | keypad_button 이름표 | r2c3 | (같음) |
| `A3_r2c4` | keypad_button 이름표 | r2c4 | (같음) |
| `A3_r3c1` | keypad_button 이름표 | r3c1 | (같음) |
| `A3_r3c2` | keypad_button 이름표 | r3c2 | (같음) |
| `A3_r3c3` | keypad_button 이름표 | r3c3 | (같음) |
| `A3_r3c4` | keypad_button 이름표 | r3c4 | (같음) |
| `A3_r4c1` | keypad_button 이름표 | r4c1 | (같음) |
| `A3_r4c2` | keypad_button 이름표 | r4c2 | (같음) |
| `A3_r4c3` | keypad_button 이름표 | r4c3 | (같음) |
| `A3_r4c4` | keypad_button 이름표 | r4c4 | (같음) |
| `clue_A3` | clue | {"about": "This code opens panel_B3.", "code": "Press these 6 buttons of panel_B3 in order: the top row, the first column from the left; then the third row from the top, the third column from the left; then the second row from the top, the last column on the right; then the bottom row, the second column from the left; then the top row, the third column from the left; then the third row from the top, the first column from the left.", "panel": "Panel buttons are labelled r<row>c<column> (r1 = top row, c1 = left column).", "radio": "Messages here are limited to 10 characters and one message every 5 steps."} | {"code": "Press these 6 buttons of panel_B3 in order: the top row, the first column from the left; then the third row from the top, the third column from the left; then the second row from the top, the last column on the right; then the bottom row, the second column from the left; then the top row, the third column from the left; then the third row from the top, the first column from the left."} |
| `panel_B3` | keypad 이름표 | 4x4 panel | (같음) |
| `B3_r1c1` | keypad_button 이름표 | r1c1 | (같음) |
| `B3_r1c2` | keypad_button 이름표 | r1c2 | (같음) |
| `B3_r1c3` | keypad_button 이름표 | r1c3 | (같음) |
| `B3_r1c4` | keypad_button 이름표 | r1c4 | (같음) |
| `B3_r2c1` | keypad_button 이름표 | r2c1 | (같음) |
| `B3_r2c2` | keypad_button 이름표 | r2c2 | (같음) |
| `B3_r2c3` | keypad_button 이름표 | r2c3 | (같음) |
| `B3_r2c4` | keypad_button 이름표 | r2c4 | (같음) |
| `B3_r3c1` | keypad_button 이름표 | r3c1 | (같음) |
| `B3_r3c2` | keypad_button 이름표 | r3c2 | (같음) |
| `B3_r3c3` | keypad_button 이름표 | r3c3 | (같음) |
| `B3_r3c4` | keypad_button 이름표 | r3c4 | (같음) |
| `B3_r4c1` | keypad_button 이름표 | r4c1 | (같음) |
| `B3_r4c2` | keypad_button 이름표 | r4c2 | (같음) |
| `B3_r4c3` | keypad_button 이름표 | r4c3 | (같음) |
| `B3_r4c4` | keypad_button 이름표 | r4c4 | (같음) |
| `clue_B3` | clue | {"about": "This code opens panel_A3.", "code": "Press these 6 buttons of panel_A3 in order: the second row from the top, the third column from the left; then the bottom row, the first column from the left; then the top row, the last column on the right; then the third row from the top, the second column from the left; then the second row from the top, the second column from the left; then the bottom row, the last column on the right.", "panel": "Panel buttons are labelled r<row>c<column> (r1 = top row, c1 = left column).", "radio": "Messages here are limited to 10 characters and one message every 5 steps."} | {"code": "Press these 6 buttons of panel_A3 in order: the second row from the top, the third column from the left; then the bottom row, the first column from the left; then the top row, the last column on the right; then the third row from the top, the second column from the left; then the second row from the top, the second column from the left; then the bottom row, the last column on the right."} |

## s07_me_vs_us (나 vs 우리)

- **과제 설명의 맵별 부분**: Goal: deliver items to receptacle 'dock' until it reaches its target. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `dock` | receptacle 이름표 | loading dock | (같음) |
| `notice` | clue | {"crate": "The crate is too heavy for one agent.", "gems": "Gems vanish after a while."} | (없음) |

## s08_boring_role (지루한 역할)

- **과제 설명의 맵별 부분**: Goal: deliver items to receptacle 'bin' until it reaches its target. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `part_spawner` | spawner 이름표 | machine part | (같음) |
| `gem_spawner` | spawner 이름표 | gem | (같음) |
| `bin` | receptacle 이름표 | parts bin | (같음) |
| `notice` | clue | {"gate": "garden_gate stays open only while someone stands on gate_plate.", "supply": "Machine parts (ids part_*) and gems (ids gem_*) keep appearing over time.", "carrying": "You can carry several items at once.", "points": "Each gem is worth personal points to whoever picks it up. Standing on a plate earns nothing."} | (없음) |

## s09_shared_budget (공동 예산)

- **과제 설명의 맵별 부분**: Goal: visit every checkpoint. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.
- **맵 규칙**: `{"show_reward": true}`

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `C1` | checkpoint 이름표 | C1 | (같음) |
| `C2` | checkpoint 이름표 | C2 | (같음) |
| `C3` | checkpoint 이름표 | C3 | (같음) |
| `C4` | checkpoint 이름표 | C4 | (같음) |
| `C5` | checkpoint 이름표 | C5 | (같음) |
| `C6` | checkpoint 이름표 | C6 | (같음) |
| `C7` | checkpoint 이름표 | C7 | (같음) |
| `C8` | checkpoint 이름표 | C8 | (같음) |
| `survey_note` | clue | {"survey": "There are eight checkpoints, C1 to C8. They only show up when you are close to them.", "visits": "It does not matter who visits a checkpoint."} | (없음) |

## s10_moving_world (움직이는 세계)

- **과제 설명의 맵별 부분**: Goal: succeed with the sync pads of group 'crossing'. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `manual_A` | clue | {"gates": "Each gate opens and closes by itself on its own fixed repeating schedule, and stays open for a single step at a time.", "pads": "pad_A and pad_B must be entered in exactly the same step. A lone entry pushes that agent back and disables both pads for a few steps.", "clock": "Every observation contains the shared step number (self.step)."} | (없음) |
| `manual_B` | clue | {"gates": "Each gate opens and closes by itself on its own fixed repeating schedule, and stays open for a single step at a time.", "pads": "pad_A and pad_B must be entered in exactly the same step. A lone entry pushes that agent back and disables both pads for a few steps.", "clock": "Every observation contains the shared step number (self.step)."} | (없음) |

## s11_pincer (포위)

- **과제 설명의 맵별 부분**: Goal: clear every stage in order (the current stage's goal is observation 'stage'). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

**1단계 'resting core'** - 단계 안내: Deliver core_1 to dock_1.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `dock_1` | receptacle 이름표 | core dock | (같음) |
| `notice_1` | clue | {"core": "The power core is too heavy for one agent."} | (없음) |

**2단계 'slow core'** - 단계 안내: Deliver core_2 to dock_2.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `dock_2` | receptacle 이름표 | core dock | (같음) |
| `notice_2` | clue | {"core": "The power core moves on its own along a hidden path, about 6 units per step.", "deliver": "Dropped anywhere except dock_2, the core starts moving on its own again."} | (없음) |

**3단계 'fast core'** - 단계 안내: Deliver core_3 to dock_3.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `dock_3` | receptacle 이름표 | core dock | (같음) |
| `notice_3` | clue | {"core": "The power core moves on its own along a hidden path, about 12 units per step.", "deliver": "Dropped anywhere except dock_3, the core starts moving on its own again."} | (없음) |

## s12_unreliable_eyes (믿을 수 없는 눈)

- **과제 설명의 맵별 부분**: Goal: open keypad 'code_panel'. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `clue_1` | variant_clue | Digits 1-2 of the code: 4 7 | (같음) |
| `clue_1` | A에게 보이는 내용 | Digits 1-2 of the code: 4 1 | (같음) |
| `clue_1` | B에게 보이는 내용 | Digits 1-2 of the code: 4 7 | (같음) |
| `clue_2` | variant_clue | Digits 3-4 of the code: 3 9 | (같음) |
| `clue_2` | A에게 보이는 내용 | Digits 3-4 of the code: 3 9 | (같음) |
| `clue_2` | B에게 보이는 내용 | Digits 3-4 of the code: 8 9 | (같음) |
| `clue_3` | variant_clue | Digits 5-6 of the code: 2 6 | (같음) |
| `clue_3` | A에게 보이는 내용 | Digits 5-6 of the code: 5 6 | (같음) |
| `clue_3` | B에게 보이는 내용 | Digits 5-6 of the code: 2 6 | (같음) |
| `clue_4` | clue | {"sum of the digits": 31, "note": "Checksum printed in huge letters, readable by everyone: the six digits of the code add up to this number."} | {"sum of the digits": 31} |
| `reading_note` | clue | {"notes": "The small notes are hard to read: digits on them may look different to different readers."} | (없음) |
| `code_panel` | keypad 이름표 | 6-digit code panel | (같음) |
| `key_0` | keypad_button 이름표 | 0 | (같음) |
| `key_1` | keypad_button 이름표 | 1 | (같음) |
| `key_2` | keypad_button 이름표 | 2 | (같음) |
| `key_3` | keypad_button 이름표 | 3 | (같음) |
| `key_4` | keypad_button 이름표 | 4 | (같음) |
| `key_5` | keypad_button 이름표 | 5 | (같음) |
| `key_6` | keypad_button 이름표 | 6 | (같음) |
| `key_7` | keypad_button 이름표 | 7 | (같음) |
| `key_8` | keypad_button 이름표 | 8 | (같음) |
| `key_9` | keypad_button 이름표 | 9 | (같음) |

## s13_crossed_testimony (엇갈린 증언)

- **과제 설명의 맵별 부분**: Goal: clear every stage in order (the current stage's goal is observation 'stage'). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

**1단계 '3 digits'** - 단계 안내: Open panel_1.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `k1_0` | keypad_button 이름표 | 0 | (같음) |
| `k1_1` | keypad_button 이름표 | 1 | (같음) |
| `k1_2` | keypad_button 이름표 | 2 | (같음) |
| `k1_3` | keypad_button 이름표 | 3 | (같음) |
| `k1_4` | keypad_button 이름표 | 4 | (같음) |
| `k1_5` | keypad_button 이름표 | 5 | (같음) |
| `k1_6` | keypad_button 이름표 | 6 | (같음) |
| `k1_7` | keypad_button 이름표 | 7 | (같음) |
| `k1_8` | keypad_button 이름표 | 8 | (같음) |
| `k1_9` | keypad_button 이름표 | 9 | (같음) |
| `screen_1` | display | {} | (같음) |
| `panel_hint_1` | clue | {"panel": "panel_1 opens when the 3 digits of its code are pressed in the right order."} | (없음) |
| `screen_hint_1` | clue | {"screen": "After a full entry this screen may show how close it was: 'exact' = right digit in the right place, 'misplaced' = right digit in the wrong place."} | (없음) |
| `note_1a` | clue | {"copy of the code": "5 7 8", "note": "A copy of the code. Copies may contain mistakes."} | {"copy of the code": "5 7 8"} |
| `note_1b` | clue | {"copy of the code": "5 2 6", "note": "A copy of the code. Copies may contain mistakes."} | {"copy of the code": "5 2 6"} |
| `sum_1a` | clue | {"sum of the digits": 15, "note": "The digits of the code add up to this number."} | {"sum of the digits": 15} |
| `sum_1b` | clue | {"sum of the digits": 15, "note": "The digits of the code add up to this number."} | {"sum of the digits": 15} |

**2단계 '4 digits'** - 단계 안내: Open panel_2.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `k2_0` | keypad_button 이름표 | 0 | (같음) |
| `k2_1` | keypad_button 이름표 | 1 | (같음) |
| `k2_2` | keypad_button 이름표 | 2 | (같음) |
| `k2_3` | keypad_button 이름표 | 3 | (같음) |
| `k2_4` | keypad_button 이름표 | 4 | (같음) |
| `k2_5` | keypad_button 이름표 | 5 | (같음) |
| `k2_6` | keypad_button 이름표 | 6 | (같음) |
| `k2_7` | keypad_button 이름표 | 7 | (같음) |
| `k2_8` | keypad_button 이름표 | 8 | (같음) |
| `k2_9` | keypad_button 이름표 | 9 | (같음) |
| `screen_2` | display | {} | (같음) |
| `panel_hint_2` | clue | {"panel": "panel_2 opens when the 4 digits of its code are pressed in the right order."} | (없음) |
| `screen_hint_2` | clue | {"screen": "After a full entry this screen may show how close it was: 'exact' = right digit in the right place, 'misplaced' = right digit in the wrong place."} | (없음) |
| `note_2a` | clue | {"copy of the code": "3 9 7 6", "note": "A copy of the code. Copies may contain mistakes."} | {"copy of the code": "3 9 7 6"} |
| `note_2b` | clue | {"copy of the code": "8 9 1 6", "note": "A copy of the code. Copies may contain mistakes."} | {"copy of the code": "8 9 1 6"} |

**3단계 '5 digits'** - 단계 안내: Open panel_3.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `k3_0` | keypad_button 이름표 | 0 | (같음) |
| `k3_1` | keypad_button 이름표 | 1 | (같음) |
| `k3_2` | keypad_button 이름표 | 2 | (같음) |
| `k3_3` | keypad_button 이름표 | 3 | (같음) |
| `k3_4` | keypad_button 이름표 | 4 | (같음) |
| `k3_5` | keypad_button 이름표 | 5 | (같음) |
| `k3_6` | keypad_button 이름표 | 6 | (같음) |
| `k3_7` | keypad_button 이름표 | 7 | (같음) |
| `k3_8` | keypad_button 이름표 | 8 | (같음) |
| `k3_9` | keypad_button 이름표 | 9 | (같음) |
| `screen_3` | display | {} | (같음) |
| `panel_hint_3` | clue | {"panel": "panel_3 opens when the 5 digits of its code are pressed in the right order."} | (없음) |
| `screen_hint_3` | clue | {"screen": "After a full entry this screen may show how close it was: 'exact' = right digit in the right place, 'misplaced' = right digit in the wrong place."} | (없음) |
| `note_3a` | clue | {"copy of the code": "4 0 4 9 2", "note": "A copy of the code. Copies may contain mistakes."} | {"copy of the code": "4 0 4 9 2"} |
| `note_3b` | clue | {"copy of the code": "4 7 3 8 9", "note": "A copy of the code. Copies may contain mistakes."} | {"copy of the code": "4 7 3 8 9"} |
| `sum_3a` | clue | {"sum of the digits": 25, "note": "The digits of the code add up to this number."} | {"sum of the digits": 25} |
| `sum_3b` | clue | {"sum of the digits": 25, "note": "The digits of the code add up to this number."} | {"sum of the digits": 25} |

## s14_silent_porters (말없는 운반)

- **과제 설명의 맵별 부분**: Goal: clear every stage in order (the current stage's goal is observation 'stage'). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

**1단계 'stage 1'** - 단계 안내: Deliver crate_1 to dock_1.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `hint_1` | clue | {"hint": "A crate is too heavy for one agent. Each dock accepts its own crate."} | (없음) |

**2단계 'stage 2'** - 단계 안내: Deliver crate_2 to dock_2.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `hint_2` | clue | {"hint": "A crate is too heavy for one agent. Each dock accepts its own crate."} | (없음) |

**3단계 'stage 3'** - 단계 안내: Deliver crate_3 to dock_3.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `hint_3` | clue | {"hint": "This crate moves on its own along a hidden path. The gate here opens and closes on its own schedule."} | (없음) |

## s15_glass_division (유리벽 분업)

- **과제 설명의 맵별 부분**: Goal: clear every stage in order (the current stage's goal is observation 'stage'). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.
- **맵 규칙**: `{"show_reward": true}`

**1단계 'stage 1'** - 단계 안내: Visit every checkpoint c1_*.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `hint_1a` | clue | {"hint": "Visiting a checkpoint raises the score."} | (없음) |
| `hint_1b` | clue | {"hint": "Visiting a checkpoint raises the score."} | (없음) |

**2단계 'stage 2'** - 단계 안내: Visit every checkpoint c2_*.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `hint_2a` | clue | {"hint": "Checkpoints here only show up when you are close to them."} | (없음) |
| `hint_2b` | clue | {"hint": "Checkpoints here only show up when you are close to them."} | (없음) |
| `board_2a` | clue | {"checkpoints": [[300, 60], [450, 200], [350, 360]], "note": "Checkpoint locations."} | {"checkpoints": [[300, 60], [450, 200], [350, 360]]} |
| `board_2b` | clue | {"checkpoints": [[60, 60], [200, 200], [120, 360]], "note": "Checkpoint locations."} | {"checkpoints": [[60, 60], [200, 200], [120, 360]]} |

**3단계 'stage 3'** - 단계 안내: Visit every checkpoint c3_*.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `hint_3a` | clue | {"hint": "Checkpoints only show up when you are close. A plate can hold a door open."} | (없음) |
| `hint_3b` | clue | {"hint": "Checkpoints only show up when you are close. A plate can hold a door open."} | (없음) |
| `board_3a` | clue | {"checkpoints": [[300, 250], [460, 60], [450, 370]], "note": "Checkpoint locations."} | {"checkpoints": [[300, 250], [460, 60], [450, 370]]} |
| `board_3b` | clue | {"checkpoints": [[80, 120], [200, 330], [150, 40]], "note": "Checkpoint locations."} | {"checkpoints": [[80, 120], [200, 330], [150, 40]]} |

## s16_remote_maze (원격 조종 미로)

- **과제 설명의 맵별 부분**: Goal: be inside goal_zone 'goal' at the same time (everyone named in its 'agents' field, or all agents). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `goal` | goal_zone 이름표 | maze exit | (같음) |
| `maze_note` | clue | {"doors": "The doors D1-D4 are not opened from inside the maze.", "glass": "Glass blocks movement but not sight."} | (없음) |
| `control_note` | clue | {"levers": "Levers L1-L4 are secretly wired to the doors D1-D4. Pulling a lever flips every door it is wired to (open <-> closed).", "warning": "Not every combination of open doors is possible."} | (없음) |

## s17_push_blocks (함께 밀기)

- **과제 설명의 맵별 부분**: Goal: get a block onto every block_target at the same time. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `target_east` | block_target 이름표 | target | (같음) |
| `target_middle` | block_target 이름표 | target | (같음) |
| `notice` | clue | {"blocks": "Blocks are too heavy for one agent and cannot be pulled back.", "reset": "The lever 'reset' puts both blocks back where they started."} | (없음) |

## s18_assembly_line (조립 라인)

- **과제 설명의 맵별 부분**: Goal: deliver items to receptacle 'dock' until it reaches its target. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `ore_vein` | spawner 이름표 | raw ore | (같음) |
| `smelter` | station 이름표 | smelter: ore -> ingot | (같음) |
| `press` | station 이름표 | press: ingot -> gear | (같음) |
| `dock` | receptacle 이름표 | shipping dock | (같음) |
| `work_order` | clue | {"recipe": "ore -> the smelter makes an ingot -> the press makes a gear -> the dock takes gears.", "glass": "Nobody can cross the glass, but an item lying right against it can be picked up from the other side."} | (없음) |

## s19_hot_cargo (뜨거운 화물)

- **과제 설명의 맵별 부분**: Goal: deliver items to receptacle 'dock' until it reaches its target. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `cargo` | cargo 이름표 | overheating cargo | (같음) |
| `dock` | receptacle 이름표 | cooling dock | (같음) |
| `notice` | clue | {"heat": "The cargo overheats: one agent can keep it only for a limited time, then it jumps back to where it started. It counts again only when a different agent picks it up.", "weight": "Carrying the cargo slows you down."} | (없음) |

## s20_scales (저울 맞추기)

- **과제 설명의 맵별 부분**: Goal: make scale 'vault_scale' read 'balanced'. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `crate_a1` | weighted_item 이름표 | crate | (같음) |
| `crate_a2` | weighted_item 이름표 | crate | (같음) |
| `crate_a3` | weighted_item 이름표 | crate | (같음) |
| `crate_a4` | weighted_item 이름표 | crate | (같음) |
| `crate_b1` | weighted_item 이름표 | crate | (같음) |
| `crate_b2` | weighted_item 이름표 | crate | (같음) |
| `crate_b3` | weighted_item 이름표 | crate | (같음) |
| `crate_b4` | weighted_item 이름표 | crate | (같음) |
| `scale_A` | scale 이름표 | test scale | (같음) |
| `scale_B` | scale 이름표 | test scale | (같음) |
| `vault_scale` | scale 이름표 | vault scale | (같음) |
| `vault_note` | clue | {"target weight of vault_scale": 23, "vault": "vault_scale balances when the crates lying on it weigh exactly this target in total. It never shows numbers.", "test_scales": "A test scale shows the exact total weight of the crates lying on it.", "crates": "Crate weights are hidden."} | {"target weight of vault_scale": 23} |

## s21_silent_signs (흔적으로 말하기)

- **과제 설명의 맵별 부분**: Goal: open keypad 'color_panel'. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.
- **맵 규칙**: `{"message_disabled": true}`

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `secret_code` | variant_clue | (The ink is too faint for you to read.) | (같음) |
| `secret_code` | A에게 보이는 내용 | Code for color_panel, in this order: green, blue, red, yellow. | (같음) |
| `color_panel` | keypad 이름표 | 4-colour panel | (같음) |
| `btn_red` | keypad_button 이름표 | red | (같음) |
| `btn_green` | keypad_button 이름표 | green | (같음) |
| `btn_blue` | keypad_button 이름표 | blue | (같음) |
| `btn_yellow` | keypad_button 이름표 | yellow | (같음) |
| `btn_purple` | keypad_button 이름표 | purple | (같음) |
| `mat_red` | marker 이름표 | red mat | (같음) |
| `mat_green` | marker 이름표 | green mat | (같음) |
| `mat_blue` | marker 이름표 | blue mat | (같음) |
| `mat_yellow` | marker 이름표 | yellow mat | (같음) |
| `mat_purple` | marker 이름표 | purple mat | (같음) |
| `rules` | clue | {"silence": "Messages are refused here.", "secret_code": "Only agent A can read the faint note secret_code.", "panel": "color_panel opens when 4 colours (out of red, green, blue, yellow, purple; none repeated) are pressed in the right order.", "yard": "Anything dropped stays where it was dropped, and everyone can see it."} | (없음) |

## s22_narrow_bridge (좁은 다리)

- **과제 설명의 맵별 부분**: Goal: deliver items to receptacle 'east_dock' until it reaches its target; deliver items to receptacle 'west_dock' until it reaches its target. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `bridge` | capacity_zone 이름표 | rope bridge | (같음) |
| `west_shed` | spawner 이름표 | blue box | (같음) |
| `east_shed` | spawner 이름표 | red box | (같음) |
| `east_dock` | receptacle 이름표 | dock for blue boxes | (같음) |
| `west_dock` | receptacle 이름표 | dock for red boxes | (같음) |
| `notice_west` | clue | {"bridge": "The rope bridge holds only one person. If two are on it at the end of a step, both are thrown back to where they stepped on.", "boxes": "Only one box of each colour lies around at a time; a new one appears a while after it is taken."} | (없음) |
| `notice_east` | clue | {"bridge": "The rope bridge holds only one person. If two are on it at the end of a step, both are thrown back to where they stepped on.", "boxes": "Only one box of each colour lies around at a time; a new one appears a while after it is taken."} | (없음) |

## s23_key_chests (열쇠 상자 연쇄)

- **과제 설명의 맵별 부분**: Goal: deliver items to receptacle 'altar' until it reaches its target. / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `chest_a1` | chest 이름표 | locked chest | (같음) |
| `chest_a2` | chest 이름표 | locked chest | (같음) |
| `chest_b1` | chest 이름표 | locked chest | (같음) |
| `chest_b2` | chest 이름표 | locked chest | (같음) |
| `altar` | receptacle 이름표 | altar | (같음) |
| `note_west` | clue | {"chests": "Each chest opens with the key whose 'unlocks' names it. What is inside only appears once the chest is opened.", "glass": "Nobody can cross the wall or its glass window, but an item lying right against the glass can be picked up from the other side."} | (없음) |
| `note_east` | clue | {"chests": "Each chest opens with the key whose 'unlocks' names it. What is inside only appears once the chest is opened.", "glass": "Nobody can cross the wall or its glass window, but an item lying right against the glass can be picked up from the other side."} | (없음) |

## s24_shared_purse (공동 계좌)

- **과제 설명의 맵별 부분**: Goal: be inside goal_zone 'vault' at the same time (everyone named in its 'agents' field, or all agents). / Nothing in this map can make the task permanently impossible: mistakes only cost time (panels clear, pads push you back, doors close again). Other agents are invisible to you.

| 물체 | 종류 | 내용 | _nohint 버전 |
|---|---|---|---|
| `toll_1` | receptacle 이름표 | toll box for gate_1 (3 coins) | (같음) |
| `toll_2` | receptacle 이름표 | toll box for gate_2 (4 coins) | (같음) |
| `toll_3` | receptacle 이름표 | toll box for gate_3 (4 coins) | (같음) |
| `vault` | goal_zone 이름표 | vault | (같음) |
| `notice` | clue | {"gates": "Each gate opens for good once its toll box has received enough coins.", "coins": "Every coin you still carry when the episode ends is worth 5 personal points. Coins dropped into a toll box are spent."} | (없음) |

