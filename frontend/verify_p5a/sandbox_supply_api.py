"""P5-A 沙盘供给链路核验：模拟增减床位 → 现有服务重算 Greedy / exact_min_cost_flow，零业务写入。"""
import json
import re
import urllib.request
from pathlib import Path

import pymysql

ROOT = Path(r"E:/Attention is all you need")
env = (ROOT / "backend" / ".env").read_text(encoding="utf-8")
test_url = re.search(r"^TEST_DATABASE_URL=(.+)$", env, re.M).group(1).strip()
m = re.match(r"mysql\+pymysql://([^:]+):([^@]+)@([^:]+):(\d+)/(\w+)", test_url)
DB = dict(host=m.group(3), port=int(m.group(4)), user=m.group(1), password=m.group(2), database=m.group(5))

TABLES = ("beds", "bed_scene_slots", "bed_allocations", "admission_requests", "preadmissions")


def counts():
    conn = pymysql.connect(**DB)
    out = {}
    with conn.cursor() as cur:
        for t in TABLES:
            cur.execute(f"select count(*) from {t}")
            out[t] = cur.fetchone()[0]
    conn.close()
    return out


def api(path, token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request("http://127.0.0.1:8000" + path, data=data,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": "Bearer " + token} if token else {})})
    return json.load(urllib.request.urlopen(req))


token = api("/api/v1/auth/login", payload={"username": "admin", "password": "admin123"})["access_token"]
snap = api("/api/v1/ward-map", token)
before = counts()
free = [b for b in snap["beds"] if b["status"] == "AVAILABLE"]
dept = free[0]["department_id"]
print("ward-map:", len(snap["beds"]), "beds;", snap["data_source"], ";free", len(free))

base = api("/api/v1/ward-map/simulate", token, {
    "scenario_kind": "SYNTHETIC_ONLY",
    "synthetic_requests": [{"scenario_id": 1, "department_id": dept, "gender": "FEMALE", "priority": "NORMAL"}],
})

template = free[0]
withbed = api("/api/v1/ward-map/simulate", token, {
    "scenario_kind": "SYNTHETIC_ONLY",
    "synthetic_requests": [{"scenario_id": 1, "department_id": dept, "gender": "FEMALE", "priority": "NORMAL"}],
    "synthetic_beds": [{"virtual_id": -1, "template_bed_id": template["id"],
                        "code": "SIM-001", "ward_id": template["ward_id"]}],
})
# 模拟「临时移除空闲床」：把模板床设为不可用
removed = api("/api/v1/ward-map/simulate", token, {
    "scenario_kind": "SYNTHETIC_ONLY",
    "synthetic_requests": [{"scenario_id": 1, "department_id": dept, "gender": "FEMALE", "priority": "NORMAL"}],
    "unavailable_bed_ids": [template["id"]],
})
after = counts()

for name, res in (("baseline", base), ("supply+1", withbed), ("supply-1", removed)):
    print(f"{name}: greedy={res['greedy']['method']} admitted={res['greedy']['admitted']} | "
          f"optimized={res['optimized']['method']} admitted={res['optimized']['admitted']} "
          f"proven_optimal={res['optimized']['proven_optimal']} | prep={res['preview_only']} nowrite={res['no_database_writes']}")

print("SIM candidate codes:", sorted({c["bed_code"] for c in withbed["candidates"] if c["bed_code"].startswith("SIM")}))
print("SIM pairs:", [p["bed_id"] for p in withbed["optimized"]["pairs"]])
print("applied_unavailable:", removed["applied_unavailable_bed_ids"])
print("tables before:", before)
print("tables after :", after)
print("IDENTICAL:", before == after)
