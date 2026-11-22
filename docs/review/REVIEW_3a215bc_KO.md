# EMS Atlas 독립 리뷰 · 커밋 3a215bc

2026-11-22 · Doyeon K. 요청으로 Claude가 작성

## 결론

**데모 시연: 가능. 운영 투입: 불가.** 0188 가상 데이터에서 MWh → 15분 reading → 위반 룰 → 검토 요청 → 상태·보고 판단까지 끊김 없이 재현됐고, 프롬프트의 SPIKE·LOW·GOLD_MISSING·REST 시나리오 값도 모두 일치했습니다.

**가장 큰 근거:** 화면이 보여주는 증거와 DB가 저장한 증거가 같다는 보장이 없습니다. DB 슬롯을 정정하면 히트맵은 새 값(raw 9999, delta 4.5, status ok)을 보이는데 SPIKE 경보는 그대로 남고, "Inspect event" 모달과 검토 요청에는 브라우저가 다시 만든 옛 값(5,381, delta 없음)이 들어갑니다. 요청에는 룰·finding ID가 구조 필드가 아니라 자유 텍스트로만 남습니다. 인증·공장별 접근 제어도 없습니다.

보조 근거: 슬롯을 지우고 다시 적재하면 남은 경보와 PK가 충돌해 하루치 배치 전체가 실패합니다. 월간 매트릭스는 데이터가 없는 10월 15–31일도 Ready로 표시합니다.

## 실행 환경과 검증 범위

검토 대상은 doyeonkim2016/ems-atlas 커밋 `3a215bc` ("Sync deployed EMS Atlas rule checks and add Korean agent review brief")입니다. 코드는 수정하지 않았고, 테스트 스크립트는 저장소 밖에 따로 두었습니다(SQL 룰 테스트는 이 PR의 `review/sql_rules_test.py`).

| 구분 | 환경 | 확인한 내용 |
| --- | --- | --- |
| 정적 서버 (실행) | `python3 -m http.server 8000`, Chrome headless | 보고 수치·차트 동작. `/api/meter-day` GET 404, POST 501, `/api/reviews` 404 → "App database unavailable", "Request status unavailable" 표시 |
| 로컬 Worker + D1 (실행) | `node build.mjs` → wrangler 4.166 `dev --local`, 두 SQL 마이그레이션 적용 | 샘플 적재, 히트맵, 검토 요청 생성·상태 변경·충돌, 14일 전체 적재 후 SQL 합계 |
| 임시 SQLite (실행) | Python sqlite3 3.53.1 | demo_v1 트리거 30개 케이스(정상·위반·경계·복수 위반), 재적재·정정·삭제 후 재적재 |
| Teams relay (실행) | 로컬 HTTPS 가짜 Workflow(202/500/20초 지연) | 재시도·중복 방지·타임아웃·export·앱 import. 실제 Teams 전송 없음 |
| 브라우저 (실행) | Playwright + Chrome, 1440px 데스크톱 / 390px 모바일 터치·reduced motion | 주요 여정 클릭 재현, 스크린샷, 계산 스타일(대비) |
| 배포 앱 (미검증) | ems-field-atlas 사이트 | 접속하지 않음. 소유자 접근 제한 가능성이 있고, Sites 소스 8c3e678과의 일치도 확인 못 함 |

**미검증으로 남긴 것:** 실제 D1(클라우드) 동작, 호스팅 인증 계층, 실제 Teams Workflow 게시와 담당자 확인, Excel에서 CSV를 열 때의 ID 변형, 스크린리더 실사용, 별도 CSV 파일럿(354태그) 데이터. 아래 표의 수치는 모두 가상 시나리오 값입니다.

## 핵심 추적 시나리오 재현

보고된 MWh에서 담당자 조치까지는 클릭으로 다다를 수 있습니다. 다만 중간에 증거의 출처가 DB에서 브라우저 생성값으로 바뀝니다(3단계 → 4단계).

1. **보고 MWh (Reporting → Reported energy, Demand, Full extract).** 화면 20.128 MWh = Chilled storage 9.39 + Air handling 10.738. 14일치를 D1에 적재하고 `SUM(delta*factor)/3600`을 SQL로 따로 계산해도 9.39 / 10.738로 일치했습니다. Unmapped compressor(계수 없음)와 Instantaneous load(kW)는 —로 제외됩니다.
2. **미터·날짜 선택.** Chilled storage · 2026-10-01 → Daily rule checks → Load sample day. 결과: 96슬롯 저장, 경보 3건 — 10:15 SPIKE, 15:15 LOW, 21:15 GOLD_MISSING.
3. **원본 reading과 룰 (DB).** 10:15 히트맵 상세: `SPIKE · demo_v1`, Reading 5381, Gold delta —, positive_spike_ignored. 10:30은 Reading 1389, delta 16 = 1389 − 1373(10:00 reading) → 10:00 기준 사용 확인. 18:00 reset은 Reading 5·delta NULL, 18:15 delta 4 = 9 − 5. 22:30 override는 Reading —·delta 6.
4. **상세 모달 (브라우저 생성).** "Inspect event and request review" → Silver 5,381 / Gold 5,381 / Previous 1,373 / No published delta / ×3.6. 화면 문구가 "다음 구간이 공백을 포함하므로 15분 배분은 알 수 없음"을 명시합니다.
5. **검토 요청.** Request review → 수신자·질문 입력 → Requests로 이동. 증거 문자열에 `Finding SIM-0188-…-41/positive_spike_ignored`와 event key가 들어가지만, DB 룰명 `SPIKE`·`demo_v1`은 없습니다.
6. **담당자 조치.** Open → In review → Resolved + Hold for correction 저장 성공. 두 탭 동시 수정 시 나중 탭은 "Another update was saved…"(409). Reported energy로 돌아오면 "Spike excluded" finding 행과 "Requests in this reporting window"에 Resolved · Hold for correction이 표시됩니다.

**정상 계산된 이상 사용(10월 2일).** 히트맵 00:00–01:45에 REST 경보 8건(delta 7–8 kWh), Reporting findings에는 "Usage in scheduled rest · 8 intervals" 1건, 요청은 사용자가 선택한 슬롯 1개 기준으로 생성됩니다. 사용량은 보고 합계에 포함됐고 모달도 "Consumption is included"라고 밝힙니다. 즉 현장은 경보 8개·finding 1개·요청 1개를 서로 다른 단위로 보게 됩니다.

**Reset·override.** 18:00 reset_anchor와 22:30 approved_override는 DB 경보를 만들지 않지만("No configured rule breached"), 브라우저 Reporting findings에는 "Reset boundary"·"Approved override"로 각각 1건씩 나타납니다. 같은 날 경보는 3건, finding은 5건으로 다릅니다.

## 사용자 여정별 결과

프롬프트의 필수 시나리오 8개 중 숫자 재현은 모두 통과했고, 실패는 증거 일치·재처리·월간 상태·Teams 연결에 모여 있습니다.

| 여정 | 결과 | 실행 근거 |
| --- | --- | --- |
| Spike와 기준값 | 통과 | 10:15 SPIKE·15:15 LOW·21:15 GOLD_MISSING, 10:15 raw 보존·delta NULL, 10:30 delta 16 = 1389−1373 |
| Reset·override | 통과(표시) / 실패(경보 일치) | 18:00 delta NULL→새 기준 5, 22:30 raw NULL·delta 6. DB 경보 0건, finding은 2건 |
| 정상 계산된 이상 사용 | 통과 | 10/2 REST 8건 → finding 1건(8 intervals), 보고 합계 포함 |
| 8가지 demo_v1 조건 | 통과(SQL 문구대로) | 임시 SQLite 30케이스 전부 기대값 일치. 단 단위 표기 변형·flatline·역행 delta는 미탐지 |
| 빈 날과 재실행 | 부분 실패 | 동일 재적재는 중복 없음. 정정 UPDATE는 재평가 안 됨, 삭제 후 재적재는 배치 전체 실패. pending/overdue 구분 불가 |
| 조사와 조치 | 부분 실패 | 상태·보고 판단·409 충돌 동작. DB와 모달 증거 불일치 재현, 룰 ID 비구조 저장 |
| Teams | 부분 실패 | 초안 링크·relay 재시도 동작. 타임아웃 후 재시도로 중복 게시, Reported energy 화면은 항상 "No matching delivery record" |
| 디자인과 비교 | 부분 통과 | 모바일 가로 스크롤 없음, reduced motion 처리 있음. 히트맵 셀 10×18px, 지도 제목 대비 약 1.1:1, 월간 매트릭스가 데이터 없는 날을 Ready로 표시 |
| 배포 브라우저 | 미검증 | 접속 안 함 |

참고로 두 점 비교 차트는 10/12 주에서만 나타났고(576 매칭 구간, +0%), 10/5 주는 전주에 목–일 4일이 있는데도 "No comparable period"입니다. 지도 핀 20개는 육안상 도시 위치와 대체로 맞았습니다(좌표 수치 검증은 안 함).

## 심각도순 이슈

높음 4건, 중간 5건, 낮음 5건(L1에 묶음)입니다. 대부분 실행으로 재현했고, 실행하지 않은 부분은 M2의 임계값 비교(코드 근거)와 L1의 Excel 변형(미검증)뿐입니다.

### H1. 상세 모달·검토 요청의 증거가 DB가 아니라 브라우저 생성값 (높음)

- **재현:** Chilled storage 10/1 적재 → `UPDATE meter_slot SET raw=9999, delta=4.5, status='ok' WHERE slot=41` → 화면 새로고침 → 10:15 선택 → Inspect event.
- **기대값:** 히트맵·모달·요청 증거가 모두 같은 저장 행(9999 / 4.5 / ok)을 보여준다.
- **실제값:** 히트맵은 "Reading 9999 · Gold delta 4.5 kWh · ok", 모달은 "Silver 5,381 / No published delta / positive_spike_ignored". 요청 증거도 모달 값으로 저장됩니다.
- **업무 영향:** 현장에 보낸 질문의 수치가 실제 저장값과 달라, 답변·보고 보류 판단의 근거가 틀릴 수 있습니다.
- **코드:** `dq-day.js:35` (`pilotEvidence(slot)`), `reported-energy.js:61-68`, `dq-store.js:9`(동일 생성 함수로 적재해 현재는 우연히 일치).
- **최소 수정/회귀:** 모달과 요청이 `/api/meter-day` 응답(event_key 포함)만 쓰도록 변경. DB 행을 바꾼 뒤 모달·요청 값이 따라가는지 테스트.

### H2. 검토 요청에 룰·버전·finding·공장 ID가 구조적으로 없음 (높음)

- **재현:** 10:15에서 요청 생성 후 `GET /api/reviews`.
- **기대값:** rule=SPIKE, version=demo_v1, finding_id, plant_id='0188', tag_id, slot이 컬럼으로 남는다.
- **실제값:** 테이블은 `id, plant INTEGER, evidence TEXT, recipient, question, state, history, version, created`뿐. plant는 지도 데모 배열 인덱스 0이고, `plant:"0188"` POST는 400. 연결은 자유 텍스트에서 `Simulated event (SIM-0188-…)` 정규식으로 복원합니다. 이력에 작성자도 없습니다.
- **업무 영향:** 룰별·공장별 미해결 집계, 감사 추적(누가 Ready to report를 눌렀나)이 불가능합니다. 문구 형식이 바뀌면 finding과 요청의 연결이 조용히 끊깁니다.
- **코드:** `0000_review_requests.sql:1`, `worker.js:19`, `reported-energy.js:67-68`, `report-desk.js:55-62,69`.
- **최소 수정/회귀:** `plant_id TEXT, tag_id TEXT, slot, rule, rule_version, finding_id, event_key, actor` 컬럼 추가, 이력은 별도 테이블. 문구를 바꿔도 연결이 유지되는지 테스트.

### H3. 재처리·정정이 경보에 반영되지 않고, 삭제 후 재적재는 배치를 통째로 실패시킴 (높음)

- **재현(임시 SQLite, `review/sql_rules_test.py`):** ① SPIKE 슬롯을 UPDATE로 정정 → ② overdue 슬롯에 늦게 도착한 값을 UPDATE → ③ 슬롯 DELETE 후 dq-store.js와 같은 3슬롯 배치 INSERT.
- **기대값:** ①② 경보 해제 또는 재평가, ③ 배치 적재 + 경보 재생성.
- **실제값:** ① SPIKE 유지, ② NO_READING 유지, ③ 삭제 후에도 SPIKE가 남고, 재적재는 `UNIQUE constraint failed: dq_alert…`로 실패, 적재 슬롯 0개.
- **업무 영향:** 정정된 데이터에 낡은 경보가 남아 보고가 불필요하게 보류되거나, 재처리 한 번으로 하루 데이터가 통째로 빠집니다.
- **코드:** `0001_meter_dq.sql:12,15`(AFTER INSERT 트리거만, version이 들어간 PK, FK 없음), `dq-store.js:11`.
- **최소 수정/회귀:** 트리거 대신 명시적 평가 단계(배치·슬롯 단위 삭제 후 재생성)와 `batch_run(id, watermark, status)` 도입. 정정·삭제·재적재·룰 버전 변경 4개 테스트.

### H4. 인증·공장별 접근 제어 없음 (높음)

- **재현:** curl로 `GET /api/reviews`(헤더 없음), `Origin` 헤더를 직접 넣은 POST.
- **기대값:** 로그인 사용자의 공장 범위만 조회·생성.
- **실제값:** 모든 요청과 수신자 이메일이 반환되고, 스크립트 POST도 200. Origin 검사는 CSRF 방어일 뿐입니다. GET에는 LIMIT·페이지도 없습니다.
- **업무 영향:** 타 공장 질의·담당자 연락처 노출, 위조 요청·상태 변경 가능.
- **코드:** `worker.js:13-14`. README도 "호스팅 환경에서 설정"으로 미룹니다.
- **최소 수정/회귀:** 호스트 인증(예: Entra ID) 헤더 검증 + `user_plant` 매핑으로 WHERE 제한. 타 공장 조회·수정이 403인지 테스트.

### M1. 월간 매트릭스가 실제 finding과 무관한 해시로 Ready/Review를 표시 (중간)

- **재현:** Overview → Monthly reporting readiness → Jakarta · Oct.
- **기대값:** 10/1·10/2(finding 7건)는 Review, 데이터 없는 10/15–31은 미판정.
- **실제값:** 10/1–19 Ready, **10/20만 Review**, 10/21–31 Ready. `(p*13+m*7+d)%83===0` 식에서 10/20이 걸린 것입니다.
- **업무 영향:** 월 단위 보고 담당자가 조사할 날을 잘못 고르고, 데이터 없는 날을 보고 가능으로 읽습니다.
- **코드:** `batches.js:27-45`.
- **최소 수정:** 일자 상태를 저장된 배치·경보에서 계산하고, 배치가 없는 날은 "No batch"로 표시.

### M2. 세 개의 룰북이 공존하고 DB 룰(demo_v1)은 Rulebook에 없음 (중간)

- **재현:** Investigation → Rulebook.
- **기대값:** 히트맵에 뜨는 SPIKE…NO_READING과 임계값이 나온다.
- **실제값:** DQ01–DQ06, OP01–OP03만 표시(GX/GA는 별도 화면). "휴지 사용"만 해도 REST(슬롯당 >2 kWh), OP02(>2 kWh), GA02(4슬롯 연속 >4 kWh) 세 정의가 있습니다.
- **업무 영향:** 같은 현상에 화면마다 판정이 다릅니다.
- **코드:** `0001_meter_dq.sql:15-27`, `rules.js:2-12,40-45`, `gold.js:77-85`.
- **최소 수정:** `rule(id, version, threshold, description)` 테이블을 단일 출처로 두고 Rulebook이 그것을 렌더.

### M3. NO_READING이 앱 경로에서 발생할 수 없음 (중간)

- **재현:** 14일 × 3태그 적재 후 `SELECT rule, count(*) FROM dq_alert`.
- **기대값:** 기대 슬롯이 안 오면 NO_READING.
- **실제값:** FACTOR 1,344 / REST 8 / SPIKE·LOW·GOLD_MISSING 각 1, NO_READING 0. 적재 코드가 `overdue`를 넣지 않고(기본 0), 빈 슬롯 행을 만드는 스케줄러도 없습니다. 적재 전 날은 `{"slots":[]}`로 pending·실패·overdue가 구분되지 않습니다.
- **업무 영향:** 미터가 통째로 죽은 날이 "저장된 배치 없음"으로만 보입니다.
- **코드:** `dq-store.js:9-11`, `dq-day.js` 빈 결과 처리.

### M4. 경보 폭주: 계수 없는 미터 1개가 14일간 1,344건 (중간)

- **실제값:** 전체 1,355건 중 99%가 Unmapped compressor의 FACTOR. 브라우저는 이를 finding 1건(1,344 intervals)으로 묶지만 DB·Teams에는 그룹 개념이 없습니다.
- **업무 영향:** 1,000개 미터에서는 설정 누락 경보가 실제 이상을 묻습니다.
- **최소 수정:** 미터 설정 결함(계수·단위)은 미터당 1건의 상태로, finding은 DB에 저장.

### M5. Teams: 타임아웃 후 재시도 시 중복 게시, 보고 화면과 ID 불일치 (중간)

- **재현:** 가짜 Workflow가 요청을 받고 20초 뒤 응답 → relay `Unknown outcome`(exit 1) → 같은 id 재실행.
- **기대값:** 채널에 1회 게시.
- **실제값:** 서버가 2회 수신. 중복 방지는 `Accepted` 기록이 있을 때만 동작합니다. 또 event.json id(`sample-jakarta-0188-1600`)와 Reported energy의 finding id 형식이 달라, 로그를 import해도 보고 화면은 항상 "No matching delivery record"입니다. import 로그는 브라우저 메모리에만 있고 `Delivered` 상태를 만드는 경로(callback)는 없습니다.
- **코드:** `teams_relay.py:34,49`, `reported-energy.js:63`, `teams.js` deliveryStatus·import.
- **최소 수정:** 서버 DB에 `incident`·`delivery_attempt` 테이블, 알림 ID = finding ID, Unknown outcome은 자동 재전송 전 확인 단계.

### L1. 기타 (낮음)

- PATCH에 `version`이 없으면 500(`D1_TYPE_ERROR`). `"4"` 문자열도 통과. Resolved → Open 역방향 전이도 무제한(`worker.js:30`).
- 히트맵 셀이 모바일에서 10×18px로 터치 대상으로 작고, 4행(:00/:15/:30/:45) 레이블이 없습니다. hover에는 값이 아니라 룰명만 나옵니다(`dq-day.js:25`).
- Overview 지도 제목 "Latest assessed day · Replay"가 rgb(36,36,38) on rgb(41,42,45), 대비 약 1.1:1로 사실상 안 보입니다. Reported energy 헤더에는 "NETWORK OPERATIONS", 푸터에는 "Plant-local readings"가 붙어 UTC 화면과 어긋납니다.
- 주간 비교는 창 시작이 7일 이내면 통째로 생략(`report-desk.js:25`). "Week of 2026-09-28"은 4일치만 포함합니다.
- CSV는 모든 값을 따옴표로 감싸지만, Excel은 따옴표 있는 숫자도 변환합니다. 17자리 tag_id와 `0188`이 변형될 위험이 있습니다(Excel 실행은 미검증).

## 개선 우선순위

한 공장 실사용 전에는 아래 세 가지를 순서대로 고치는 것을 권합니다. 세 가지가 끝나야 "화면의 숫자를 근거로 보고 여부를 정한다"는 제품의 핵심 약속이 성립합니다.

### 한 공장 실사용 전 필수 세 가지

1. **증거·KPI의 단일 출처화 (H1, H2, M1, M4).** 히트맵·상세 모달·검토 요청·월간 매트릭스·finding을 모두 DB의 같은 행에서 읽게 합니다. 요청에는 `plant_id, tag_id, slot_utc, event_key, rule, rule_version, finding_id, actor`를 컬럼으로 저장합니다. 회귀 테스트: DB 행 수정 → 모달·요청·매트릭스가 같은 값을 보이는지, 보고 MWh가 SQL 합계와 같은지.
2. **일일 배치 적재·재처리 모델 (H3, M3).** `batch_run(plant, day, watermark, status, row_count)`를 두고, 승인된 cadence로 기대 슬롯을 만든 뒤 pending / received / overdue를 구분합니다. 룰 평가는 트리거가 아니라 슬롯·배치 단위의 멱등 재평가(기존 경보 대체)로 바꿉니다. 화면에는 "데이터 최신 시각"을 표시합니다. 회귀 테스트: 정정·삭제 후 재적재·늦은 도착·부분 실패 후 재실행.
3. **인증·공장별 접근 제어·감사 이력 (H4, L1).** 호스트 인증 사용자를 서버에서 확인하고, 공장 범위로 조회·수정을 제한합니다. 상태 전이 규칙과 보고 판단 변경자를 기록하고, 입력 오류는 500이 아니라 400으로 돌려줍니다.

바로 다음은 Teams 상태 추적(M5)입니다. 한 공장에서는 수동 초안으로 버틸 수 있지만, 알림 ID를 finding ID로 통일하고 전송 시도를 서버 DB에 남겨야 합니다.

### 20개 공장·약 1,000개 미터 확장 시 필요한 것

- **조회 범위·페이지:** `GET /api/reviews`와 경보 조회에 공장·기간·상태 필터와 커서 페이지. 현재는 전체 반환.
- **경보 그룹화:** 미터 설정 결함은 미터당 1건, 연속 위반은 DB finding으로 묶기. 현재 비율이면 FACTOR만 하루 미터당 96건입니다.
- **배치 최신성 보드:** 공장별 watermark·마감(현지 08:00)·지연 상태를 실제 `batch_run`에서 계산. 현재 Overview는 고정 fixture입니다.
- **룰 버전 관리:** 공장별 threshold·휴지 달력·단위 정규화('kWh'/'kwh'), 재버전 시 어느 기간을 재평가할지 기록. 현재 REST는 Chilled storage 10/2 00:00–02:00이 코드에 하드코딩돼 있습니다(`dq-store.js:9`, `report-desk.js:7`).
- **legacy_direct_delta / vee_v1 경계:** 2026-07-01 전후 비교 차트에 방법론 변경선을 표시. 현재 앱에는 이 구분이 없습니다.
- **Teams:** `incident`·`delivery_attempt` 영구 테이블, Workflow 수락과 채널 게시·담당자 확인을 구분하는 callback, 멱등 키.
- **사용성:** 모바일 히트맵 터치 영역 24px 이상, 행 레이블, hover에 값 표시. 여러 시간대의 공장을 동시에 볼 때 UTC/현지 시각 전환 기준을 한 가지로 통일.
