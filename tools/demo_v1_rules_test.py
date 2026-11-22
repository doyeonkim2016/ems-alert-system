"""Independent check of the demo_v1 trigger rules in 0001_meter_dq.sql using an in-memory SQLite DB.

Usage: python3 review/sql_rules_test.py <repo_root> [result.json]
"""
import sqlite3, sys, json
from pathlib import Path

repo = Path(sys.argv[1])
db = sqlite3.connect(":memory:")
for f in ["0000_review_requests.sql", "0001_meter_dq.sql"]:
    db.executescript((repo / f).read_text())

COLS = "plant,tag,slot,event_key,status,raw,delta,unit,factor,running,silver,gold,rest,overdue"
BASE = dict(plant="0188", tag="T", event_key="k", status="ok", raw=100.0, delta=5.0, unit="kWh",
            factor=3.6, running=1, silver=1, gold=1, rest=0, overdue=0)
slot = 0
def ins(**kw):
    global slot
    slot += 1
    row = {**BASE, **kw, "slot": slot}
    db.execute(f"INSERT INTO meter_slot({COLS}) VALUES ({','.join('?'*14)})", [row[c] for c in COLS.split(',')])
    got = sorted(r[0] for r in db.execute("SELECT rule FROM dq_alert WHERE slot=?", (slot,)))
    return got

cases = [
 ("정상 슬롯", {}, []),
 ("SPIKE 위반", dict(status="positive_spike_ignored", delta=None), ["SPIKE"]),
 ("LOW 위반", dict(status="low_reading_ignored", delta=None), ["LOW"]),
 ("reset_anchor (delta NULL)", dict(status="reset_anchor", delta=None, raw=5), []),
 ("approved_override (Silver 없음, Gold 있음, overdue=0)", dict(status="approved_override", silver=0, raw=None), []),
 ("approved_override + overdue=1", dict(status="approved_override", silver=0, raw=None, overdue=1), []),
 ("override 상태값 대소문자 변형 + overdue=1", dict(status="Approved_Override", silver=0, raw=None, overdue=1), ["NO_READING"]),
 ("GOLD_MISSING 위반", dict(gold=0, status="silver_only", delta=None), ["GOLD_MISSING"]),
 ("FACTOR 위반", dict(factor=None, unit="pulse"), ["FACTOR"]),
 ("FACTOR 경계: factor=0", dict(factor=0.0), []),
 ("FACTOR 경계: delta NULL·factor NULL", dict(factor=None, delta=None), []),
 ("FACTOR: power 태그(running=0)·factor NULL", dict(running=0, factor=None, unit="kW"), []),
 ("REST 경계 delta=2.0", dict(rest=1, delta=2.0), []),
 ("REST 위반 delta=2.001", dict(rest=1, delta=2.001), ["REST"]),
 ("REST: 단위 'kwh'(소문자)", dict(rest=1, delta=50.0, unit="kwh"), []),
 ("REST: 단위 'MWh' delta=0.5 (=500 kWh)", dict(rest=1, delta=0.5, unit="MWh"), []),
 ("REST: 단위 ' kWh '(공백)", dict(rest=1, delta=50.0, unit=" kWh "), []),
 ("REST: 단위 NULL", dict(rest=1, delta=50.0, unit=None), ["UNIT"]),
 ("UNIT 위반 ''", dict(unit=""), ["UNIT"]),
 ("UNIT 위반 '   '", dict(unit="   "), ["UNIT"]),
 ("UNIT: Silver 없음·unit 공백", dict(silver=0, unit=""), []),
 ("VALUE 위반", dict(raw=None), ["VALUE"]),
 ("NO_READING 위반", dict(silver=0, raw=None, delta=None, status=None, gold=0, overdue=1), ["NO_READING"]),
 ("Silver 없음·overdue=0 (pending과 구분 불가)", dict(silver=0, raw=None, delta=None, status=None, gold=0), []),
 ("음수 delta (rollover/역행)", dict(delta=-500.0), []),
 ("거대 delta 1e9, status ok", dict(delta=1e9), []),
 ("flatline: delta=0 반복", dict(delta=0.0), []),
 ("복수 위반: Silver only + raw NULL + unit 공백", dict(gold=0, raw=None, unit="", status="silver_only", delta=None), ["GOLD_MISSING","UNIT","VALUE"]),
 ("복수 위반: spike + factor NULL(delta 존재)", dict(status="positive_spike_ignored", factor=None), ["FACTOR","SPIKE"]),
 ("복수 위반: REST + FACTOR", dict(rest=1, delta=9.0, factor=None), ["FACTOR","REST"]),
]
results = []
fail = 0
for name, kw, exp in cases:
    got = ins(**kw)
    ok = got == sorted(exp)
    fail += not ok
    results.append(dict(case=name, expected=sorted(exp), actual=got, ok=ok))
    print(("PASS" if ok else "FAIL"), name, "기대", sorted(exp), "실제", got)

print("\n--- 재적재 / 정정 / 재버전 ---")
# 1) duplicate insert with ON CONFLICT DO NOTHING (same as dq-store.js)
db.execute(f"INSERT INTO meter_slot({COLS}) VALUES ('0188','R',1,'k','positive_spike_ignored',1,NULL,'kWh',3.6,1,1,1,0,0)")
db.execute(f"INSERT INTO meter_slot({COLS}) VALUES ('0188','R',1,'k2','ok',1,5,'kWh',3.6,1,1,1,0,0) ON CONFLICT(plant,tag,slot) DO NOTHING")
print("중복 재적재 후 slot 행/alert:", db.execute("SELECT count(*),max(event_key) FROM meter_slot WHERE tag='R'").fetchone(),
      db.execute("SELECT rule FROM dq_alert WHERE tag='R'").fetchall())
# 2) plain duplicate without ON CONFLICT
try:
    db.execute(f"INSERT INTO meter_slot({COLS}) VALUES ('0188','R',1,'k3','ok',1,5,'kWh',3.6,1,1,1,0,0)")
    print("plain INSERT 중복: 성공(예상 밖)")
except sqlite3.IntegrityError as e:
    print("plain INSERT 중복: IntegrityError", e)
# 3) correction via UPDATE: does the alert disappear?
db.execute("UPDATE meter_slot SET status='ok', delta=5 WHERE tag='R' AND slot=1")
print("UPDATE 정정 후 alert:", db.execute("SELECT rule FROM dq_alert WHERE tag='R'").fetchall())
# 4) late arrival: overdue slot later receives a reading via UPDATE
db.execute(f"INSERT INTO meter_slot({COLS}) VALUES ('0188','L',1,NULL,NULL,NULL,NULL,NULL,NULL,1,0,0,0,1)")
db.execute("UPDATE meter_slot SET silver=1,gold=1,raw=10,delta=2,unit='kWh',factor=3.6,status='ok',overdue=0 WHERE tag='L'")
print("늦은 도착 UPDATE 후 NO_READING 유지?:", db.execute("SELECT rule FROM dq_alert WHERE tag='L'").fetchall())
# 5) INSERT OR REPLACE path (delete+insert): alert stale + new
db.execute(f"INSERT OR REPLACE INTO meter_slot({COLS}) VALUES ('0188','L',1,'k','ok',10,2,'kWh',3.6,1,1,1,0,0)")
print("INSERT OR REPLACE 후 alert:", db.execute("SELECT rule,version FROM dq_alert WHERE tag='L'").fetchall())
# 6) slot semantics: no date column
print("meter_slot 컬럼:", [r[1] for r in db.execute("PRAGMA table_info(meter_slot)")])
print("dq_alert 컬럼:", [r[1] for r in db.execute("PRAGMA table_info(dq_alert)")])
print("reviews 컬럼:", [(r[1], r[2]) for r in db.execute("PRAGMA table_info(reviews)")])
print("trigger 목록:", [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")])
print("\n총", len(cases), "케이스 중 기대와 다른 결과", fail)
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(results, ensure_ascii=False, indent=1))

print("\n--- 재처리: 슬롯 삭제 후 동일 슬롯 재적재 ---")
db.execute(f"INSERT INTO meter_slot({COLS}) VALUES ('0188','D',1,'k','positive_spike_ignored',1,NULL,'kWh',3.6,1,1,1,0,0)")
db.execute("DELETE FROM meter_slot WHERE tag='D'")
print("삭제 후 남은 alert:", db.execute("SELECT rule FROM dq_alert WHERE tag='D'").fetchall())
try:
    db.execute(f"INSERT INTO meter_slot({COLS}) VALUES ('0188','D',1,'k','positive_spike_ignored',1,NULL,'kWh',3.6,1,1,1,0,0)")
    print("재적재 성공")
except sqlite3.IntegrityError as e:
    print("재적재 실패:", e)
# batch of 3 slots where only slot 1 conflicts -> whole statement?
rows=json.dumps([[1,'k','positive_spike_ignored',1,None,'kWh',3.6,1,1,1,0],[2,'k','ok',1,5,'kWh',3.6,1,1,1,0],[3,'k','ok',1,5,'kWh',3.6,1,1,1,0]])
fields=",".join(f"json_extract(value,'$[{i}]')" for i in range(11))
try:
    db.execute("INSERT INTO meter_slot(plant,tag,slot,event_key,status,raw,delta,unit,factor,running,silver,gold,rest) SELECT ?,?,"+fields+" FROM json_each(?) WHERE true ON CONFLICT(plant,tag,slot) DO NOTHING",('0188','D',rows))
    print("배치 성공")
except sqlite3.IntegrityError as e:
    print("dq-store.js 형태 배치(3슬롯) 실패:", e, "/ 적재된 슬롯 수:", db.execute("SELECT count(*) FROM meter_slot WHERE tag='D'").fetchone()[0])
