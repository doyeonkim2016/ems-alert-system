# EMS Alert System

공장 에너지 미터(서브미터) reading을 **일일 배치** 기준으로 모니터링하는 웹앱 프로토타입입니다. [EMS Atlas](https://github.com/doyeonkim2016/ems-atlas) 커밋 `3a215bc`를 리뷰한 뒤, 목적을 "보고 검토 워크플로"에서 "모니터링"으로 다시 잡고 새로 설계했습니다.

> 모든 값은 생성된 샘플 데이터입니다. 값은 생성했지만, **컬럼은 실제 스키마에 있는 것만** 씁니다(예외는 아래 [데이터](#데이터) 참고).

## 무엇을 보여주나

1. **에너지 reading 시각화**: 공장·미터별 15분 사용량, 일·월 단위 MWh, Supply와 Demand 서브미터 구분.
2. **DQ 룰이 어디에 적용됐고 무엇이 걸렸나**: 슬롯마다 8개 DQ 룰의 Pass / Alert / n/a.
3. **DQ를 통과했지만 평소와 다른 데이터**: 서브미터별 baseline 기반 이상 탐지(누수, 미터 고착, 계단형 변화 등).
4. **어떤 룰이 있고 알림이 발생했나**: 룰북과 룰별 발생 이력, 압축된 알림, 공장별 일일 알림 메시지.

## 실행

빌드가 필요 없는 단일 HTML 파일입니다.

```bash
python3 -m http.server 8000
# http://localhost:8000 열기
```

`index.html`을 브라우저로 바로 열어도 동작합니다. 외부 요청은 Google Fonts뿐이고, 없으면 기본 글꼴로 표시됩니다.

## 화면 구성

원래 EMS Atlas의 Reporting / Investigation / Operations 섹션 구조를 따릅니다.

| 섹션 | 화면 | 내용 |
|---|---|---|
| Reporting | Network overview | 기간 전환(Latest batch / Month / 12 months). 지도, 공장×일 그리드, 공장×월 상태 막대, 네트워크 에너지 차트 |
| Reporting | Plant meters | Supply·Demand 미터 목록, 기간별 MWh와 일별 추이, 서브미터가 측정하지 않는 공급량 |
| Investigation | Meter readings | 7일 15분 사용량과 baseline 밴드, 96슬롯 하루 패널, 슬롯별 룰 적용 결과와 observation 행 |
| Investigation | Rulebook | DQ 8개(demo_v1) + 이상 탐지 1개(baseline_v1), 이번 배치 발생 여부, 12개월 발생 이력 |
| Operations | Alert inbox | `dq_alert` 행을 미터·룰·날짜 단위로 압축한 알림(New / Ongoing / Earlier) |
| Operations | Daily notification | 배치당 공장별 메시지 1건. 배치가 완전하고 알림이 없으면 보내지 않음 |
| Operations | Daily ingestion | 공장×일 배치 도착 현황(완전 / 부분 / 없음) |
| Operations | Data model | 사용하는 테이블과 컬럼, 테이블별 CSV 복사 |

## 설계 결정

- **수집 주기는 하루 1회.** 모든 판단은 일일 배치 단위입니다. 15분 단위로 즉시 알릴 수 없으므로 알림도 압축합니다.
- **알림 압축:** 슬롯마다 생기는 `dq_alert` 행을 미터·룰·UTC 날짜당 1건으로 묶습니다. FactorToMJ가 없는 미터처럼 설정 문제는 미터당 1건으로 둡니다. 예시 데이터에서는 28일치 7,460행이 46건이 됩니다.
- **알림 상태:** 전날에도 같은 미터·룰이 발생했으면 Ongoing, 아니면 New. 하루를 다시 적재하면 그날의 알림을 교체합니다.
- **일일 알림:** 공장별로 하루 1건, 새로 생긴 것과 계속 열려 있는 것을 구분합니다.
- **Supply와 Demand는 합치지 않습니다.** 서브미터 합계와 공급 합계를 따로 보여 이중 계산을 막고, 그 차이를 "서브미터가 측정하지 않는 공급"으로 표시합니다.
- **날짜 경계는 UTC.** 스키마에 있는 `timestamp_utc`를 기준으로 합니다.

## DQ와 이상 탐지 룰

| 룰 | 버전 | 조건 |
|---|---|---|
| SPIKE | demo_v1 | `delta_status = 'positive_spike_ignored'` |
| LOW | demo_v1 | `delta_status = 'low_reading_ignored'` |
| GOLD_MISSING | demo_v1 | Silver 행은 있는데 Gold 행이 없음 |
| FACTOR | demo_v1 | running_total, `published_value` 있음, `FactorToMJ` 없음 |
| REST | demo_v1 | `rest = 1`, `engUnit = 'kWh'`, `published_value > 2` |
| UNIT | demo_v1 | Silver `engUnit`이 공백 |
| VALUE | demo_v1 | `silver_raw_value`가 null |
| NO_READING | demo_v1 | `overdue = 1`이고 Silver 행 없음 |
| BASELINE_Z | baseline_v1 | DQ를 통과한 running_total 행에서, 같은 요일·같은 슬롯의 최근 3주 중앙값 대비 \|차이\| ÷ spread ≥ 4가 **2슬롯 이상 연속** |

- DQ 8개는 EMS Atlas D1 트리거(`0001_meter_dq.sql`)와 같은 조건입니다.
- spread = max(1.4826 × MAD, 중앙값의 10%, 2 kWh).
- 한 슬롯만 튀는 값은 이상으로 보지 않습니다.

## 데이터

스키마에 있는 테이블 7개와 제안 테이블 1개를 씁니다.

| 테이블 | 출처 | 용도 |
|---|---|---|
| `meter_catalog` | CSV | 미터 메타데이터, 계층, Supply/Demand 구분 |
| `selected_tag_observations_one_day` | CSV | 15분 reading(Silver/Gold), 모든 룰의 입력 |
| `contributions_weekly` | CSV | 주별 Gold 에너지 |
| `silver_coverage_weekly` | CSV | 주별 Silver 관측 수 |
| `selected_tag_hourly` | CSV | 시간별 Gold 기여(아직 화면 없음) |
| `meter_slot` | D1 | 룰 평가 입력(`rest`, `overdue`) |
| `dq_alert` | D1 | 룰 발생 기록 |
| `daily_meter_summary` | **제안** | Silver/Gold를 plant·tag·UTC 날짜로 묶은 Gold 집계 + 룰별 `dq_alert` 건수. 월·연 화면용 |

- `daily_meter_summary`는 새 원천 데이터가 아닙니다. 기존 컬럼의 count/sum이고, 같은 일일 배치에서 만들며 하루를 재적재하면 다시 계산합니다.
- 유일한 가정은 `expected_rows`(15분 cadence → 96)입니다.

**스키마 밖 입력은 하나뿐입니다.** 지도에 쓰는 공장 좌표가 스키마에 없어 작은 참조 목록으로 넣었습니다. 도시 이름은 `hierarchy_path`의 첫 부분과 같습니다.

**샘플 데이터 범위**
- 20개 공장 × 8개 태그(Supply 2, Demand 6).
- 일 단위 요약: 2025-11-01부터.
- 15분 상세: 2026-10-01 ~ 10-28. 이 구간의 요약은 15분 행에서 계산하므로 화면 간 수치가 항상 일치합니다.

**심어둔 사례**
- Jakarta 0188 Air compressor 1 (2026-10-01): spike, low, reset, Silver-only, override.
- Jakarta 0188 Air compressor 1 (10/20부터): 야간 압축공기 누수. DQ는 통과하고 BASELINE_Z가 잡습니다.
- Jakarta 0188 블로우 성형기: 10/25 일요일 휴지 시간에 가동(REST).
- Shanghai 0173 칠러: 10/24부터 계단형 증가.
- Sydney 0211 충전기: 10/26 미터 고착.
- 계수가 없는 미터: Shanghai·Mexico City의 폐수 펌프(FACTOR).
- 배치: Pune 0193은 10/28 배치 누락, Sydney 0211은 10/28 부분 배치.
- Mexico City 0295: 10/27 단위 공백(UNIT).
- Bangkok 0204: 10/28 값 누락(VALUE).

## 디렉터리

```
index.html                         웹앱(단일 파일)
docs/IMPROVEMENTS_KO.md            다음 개선점
docs/review/REVIEW_3a215bc_KO.md   EMS Atlas 3a215bc 독립 리뷰
tools/demo_v1_rules_test.py        EMS Atlas SQL 룰(demo_v1) 재현 테스트
```

`tools/demo_v1_rules_test.py`는 EMS Atlas 저장소 경로를 인자로 받아, 그 저장소의 SQL 마이그레이션을 메모리 SQLite에 적용하고 30개 케이스와 재처리 시나리오를 확인합니다.

```bash
python3 tools/demo_v1_rules_test.py ../ems-atlas
```

## 진행 경과

1. EMS Atlas `3a215bc` 독립 리뷰. MWh → reading → 룰 → 조치 추적을 실행으로 재현했습니다([보고서](docs/review/REVIEW_3a215bc_KO.md)).
2. 리뷰의 개선 3가지(증거 단일 출처, 배치 재처리, 공장별 접근 제어)를 보여주는 추적 프로토타입을 만들었습니다.
3. 목적을 모니터링으로 재정의하고 이름을 EMS Alert System으로 바꿨습니다.
   - 스키마 컬럼만 쓰도록 정리했습니다.
   - 일일 배치와 알림 압축을 넣었습니다.
   - 서브미터 이상 탐지를 넣었습니다.
4. 월·12개월 기간 뷰와 `daily_meter_summary`(제안)를 추가했습니다.
