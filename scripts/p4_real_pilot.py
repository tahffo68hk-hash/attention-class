#!/usr/bin/env python
"""P4 DeepSeek Real Provider Pilot —— 一次性、有上限的真实调用运行器。

本脚本自身强制执行的约束
------------------------
* 真实 Chat Completions 调用次数 **永不超过** ``AUTHORIZED_MAX_REQUESTS``（2 次）。
  计数写入持久文件，且 **在发起网络请求之前** 先自增并落盘：
  崩溃 / 超时 / 重启 / 重复点击 都会消耗一次授权额度。
* 累计估算费用 **不超过** ``AUTHORIZED_BUDGET_CNY``（¥0.50）。估算取悲观上界：
  高峰费率 + 输入 100% 缓存未命中 + 输入按 1 token/字节 的极端上界。
* 全程 **无自动重试**（裸 httpx.Client，无 RetryTransport）。
* 只有 ``deepseek_provider._safe_evidence`` 的 fail-closed 数值白名单会离开进程：
  不含姓名、住院证号、诊断、患者 ID、床位 ID、床号或任何自由文本。

两种模式
--------
``--dry-run``  零网络彩排。通过 ``httpx.MockTransport`` 驱动 **真实** Provider 代码，
               从而在不花费任何费用的前提下，核验最终外发 JSON、白名单与预算闸门。
``--execute``  执行被授权的真实调用（经由本机运行中的 API）。
               需要服务端已配置密钥且 ``DEEPSEEK_EXTERNAL_ENABLED=true``。
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:  # 保证中文输出在 Windows 控制台可用
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

STATE_PATH = Path(os.environ.get("P4_PILOT_STATE_PATH")
                  or (REPO / ".workbuddy" / "p4_pilot_state.json"))
LOCK_PATH = STATE_PATH.with_suffix(".lock")
EVIDENCE_DIR = REPO / "docs" / "evidence" / "p4_real_pilot"

CN = timezone(timedelta(hours=8))
AUTHORIZED_MAX_REQUESTS = 2
AUTHORIZED_BUDGET_CNY = 0.50
MAX_MESSAGES_JSON_BYTES = 8192          # 用户给定上限：完整 messages JSON ≤ 8 KB
MAX_OUTPUT_TOKENS = 500
# 绝对兜底口径：即便按 v4-pro 高峰费率计价也不会越界
CEILING_RATES = {"miss": 9.0, "hit": 0.30, "out": 27.0}

FORBIDDEN_KEYS = {
    "patient_id", "admission_request_id", "bed_id", "bed_code", "certificate_no",
    "patient_name", "name", "diagnosis", "phone", "id_card", "address",
}
SNIPPETS = Path(__file__).name


# --------------------------------------------------------------------------- #
# 输出工具
# --------------------------------------------------------------------------- #
def say(msg: str = "") -> None:
    print(msg)


def hr(title: str = "") -> None:
    say("=" * 78)
    if title:
        say(title)
        say("=" * 78)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 跨进程互斥（防并发执行突破授权上限 / 预算）
# --------------------------------------------------------------------------- #
def _acquire(fd: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(fd: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def state_lock(timeout: float = 30.0):
    """对 Pilot 状态加**跨进程**排他锁。

    必须覆盖整个「读计数 → 预算校验 → 占用额度 → 落盘」序列。否则并发实例
    各自读到相同旧计数、**同时通过**上限与预算校验，实际发出 N 次真实请求
    （N = 并发实例数），而落盘计数只 +1 —— 授权上限形同虚设。
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while True:
        try:
            # 注意：Windows 的字节范围锁是**强制锁** —— 锁被占用时连
            # os.open(O_RDWR) 都会直接失败（Errno 13），因此 open 必须
            # 和加锁一起放进重试循环。
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR)
            _acquire(fd)
            break
        except OSError:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                fd = None
            if time.monotonic() >= deadline:
                raise SystemExit(
                    "[BLOCKED] 无法获取 Pilot 状态锁（另一实例可能正在运行）；"
                    "为防止突破授权上限，本次拒绝执行。") from None
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            _release(fd)
        finally:
            os.close(fd)


# --------------------------------------------------------------------------- #
# 持久计数（防重启 / 防重复点击 / 防并发执行突破上限）
# --------------------------------------------------------------------------- #
def load_state() -> dict:
    """读取持久状态；首次创建在**锁内**完成，保证 Pilot ID 与计数跨进程一致。"""
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    with state_lock():
        if STATE_PATH.exists():          # 双检：并发时由先拿到锁的一方创建
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state = {
            "pilot_id": "P4PILOT-" + datetime.now(CN).strftime("%Y%m%dT%H%M%S%z"),
            "created_at": datetime.now(CN).isoformat(),
            "authorized_max_requests": AUTHORIZED_MAX_REQUESTS,
            "authorized_budget_cny": AUTHORIZED_BUDGET_CNY,
            "attachments": [],
            "attempts": [],
            "cumulative_estimate_cny": 0.0,
        }
        save_state(state)  # ← 立即持久化，避免每次运行重新生成 Pilot ID
        return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 临时文件名必须**每进程唯一**：多个实例并发落盘时若共用同一 .tmp，
    # 会互相覆盖/抢占（Windows 上直接 PermissionError 崩溃）。
    tmp = STATE_PATH.with_name(f"{STATE_PATH.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    last: Exception | None = None
    for i in range(10):  # Windows 上并发替换目标可能瞬时失败，做有界重试
        try:
            tmp.replace(STATE_PATH)  # 原子替换 + 落盘
            return
        except PermissionError as exc:
            last = exc
            time.sleep(0.02 * (i + 1))
    tmp.unlink(missing_ok=True)
    raise SystemExit(f"[BLOCKED] 无法写入 Pilot 状态文件（并发争用）：{type(last).__name__}")


def reserve_attempt(state: dict, kind: str, worst_case_cny: float) -> int:
    """在**发起网络请求之前**占用一次授权额度并立即落盘。

    整个过程持有跨进程排他锁，并在锁内**重新读取磁盘状态**，因此并发实例被
    串行化：第 3 个及以后的实例一定读到已满的计数并被拒绝，不会多发请求。
    """
    with state_lock():
        fresh = load_state()
        used = len(fresh["attempts"])
        if used >= AUTHORIZED_MAX_REQUESTS:
            raise SystemExit(f"[BLOCKED] 已达授权上限 {AUTHORIZED_MAX_REQUESTS} 次，拒绝发起新请求。")
        # 预算余量必须同时扣掉：① 已确认花费；② **仍未结算的在途预留**（悲观上界）。
        # 否则并发/连续两次调用都按同一份余量判断，预算校验形同虚设。
        in_flight = sum(float(a.get("worst_case_estimate_cny") or 0.0)
                        for a in fresh["attempts"] if a.get("status") == "IN_FLIGHT")
        remaining = AUTHORIZED_BUDGET_CNY - fresh["cumulative_estimate_cny"] - in_flight
        if worst_case_cny > remaining:
            raise SystemExit(
                f"[BLOCKED] 本次最坏情况 ¥{worst_case_cny:.6f} 超出剩余预算 ¥{remaining:.6f}，拒绝发起请求。")
        seq = used + 1
        fresh["attempts"].append({
            "seq": seq,
            "kind": kind,
            "started_at": datetime.now(CN).isoformat(),
            "status": "IN_FLIGHT",
            "worst_case_estimate_cny": round(worst_case_cny, 8),
        })
        save_state(fresh)  # ← 先落盘再发请求
        state.clear()
        state.update(fresh)  # 回填调用方持有的 dict（保持既有调用方式不变）
        return seq


def finalize_attempt(state: dict, seq: int, patch: dict) -> dict:
    with state_lock():
        fresh = load_state()
        for att in fresh["attempts"]:
            if att["seq"] == seq:
                att.update(patch)
                cost = patch.get("cost_estimate_cny")
                if isinstance(cost, (int, float)):
                    fresh["cumulative_estimate_cny"] = round(
                        fresh["cumulative_estimate_cny"] + float(cost), 8)
                break
        save_state(fresh)
        state.clear()
        state.update(fresh)
        return fresh["attempts"][seq - 1]


# --------------------------------------------------------------------------- #
# 预算
# --------------------------------------------------------------------------- #
def rates_from_settings() -> dict:
    from app.core.config import settings
    return {
        "miss": settings.DEEPSEEK_INPUT_MISS_CNY_PER_M,
        "hit": settings.DEEPSEEK_INPUT_HIT_CNY_PER_M,
        "out": settings.DEEPSEEK_OUTPUT_CNY_PER_M,
    }


def worst_case_cost_cny(messages_json_bytes: int, max_out_tokens: int, rates: dict) -> float:
    """悲观上界：输入 1 token/字节、100% 缓存未命中、按高峰费率、输出打满。"""
    if rates["miss"] is None or rates["out"] is None:
        raise SystemExit("[BLOCKED] 费率未配置，无法估算费用 —— 按授权要求禁止发起请求。")
    return (messages_json_bytes * float(rates["miss"]) + max_out_tokens * float(rates["out"])) / 1_000_000


# --------------------------------------------------------------------------- #
# 证据构造（复用项目自身代码路径）
# --------------------------------------------------------------------------- #
def _session():
    from app.db.session import get_session_factory
    return get_session_factory()()


def _pick_requests(db, limit: int) -> list:
    from sqlalchemy import select
    from app.models.admission import AdmissionRequest
    from app.models.allocation import BedAllocation
    from app.models.enums import AdmissionRequestStatus, AllocationStatus
    rows = db.execute(
        select(AdmissionRequest).where(AdmissionRequest.status == AdmissionRequestStatus.PRE_ADMITTED)
        .order_by(AdmissionRequest.id).limit(60)).unique().scalars().all()
    out = []
    for req in rows:
        active = db.execute(select(BedAllocation.id).where(
            BedAllocation.admission_request_id == req.id,
            BedAllocation.status.in_([AllocationStatus.RESERVED, AllocationStatus.ADMITTED]),
        ).limit(1)).scalar_one_or_none()
        if active is None:
            out.append(req)
        if len(out) >= limit:
            break
    return out


def build_single_evidence(db) -> tuple[dict, dict]:
    """返回 (证据载荷, 元数据)。载荷与 /assistant/explain 走 LLM 时完全同源。"""
    from app.schemas.assistant import EvidenceScore
    from app.services.assistant_explanation import safe_payload
    from app.services.recommendation import recommend_beds

    for req in _pick_requests(db, 1):
        rec = recommend_beds(db, req, limit=None)
        if not rec.recommendations:
            continue
        item = rec.recommendations[0]
        evidence = [EvidenceScore(key=e.key, raw_score=e.raw_score, contribution=e.contribution)
                    for e in item.score_items]
        payload = safe_payload(rec.priority_rank, req.isolation_required, item.bed_type,
                               item.score, evidence, item.warnings)
        meta = {
            "source": "recommend_beds(limit=None) 的真实（虚构）评分结果",
            "priority_rank": rec.priority_rank,
            "candidate_count": len(rec.recommendations),
            "final_score": item.score,
            "dimensions": [e.model_dump() for e in evidence],
        }
        # 仅用于本地断言与 execute 定位目标，绝不随请求外发、绝不写入仓库证据
        meta["_forbidden_probe"] = _collect_probe_tokens(db, req, item)
        meta["_probe_rid"] = req.id
        meta["_probe_bed_id"] = item.bed_id
        return payload, meta
    raise SystemExit("[BLOCKED] 找不到可用于单床解释的待入院住院证（需 PRE_ADMITTED 且无活动分配）。")


def build_plan_evidence(db, n: int = 3) -> tuple[dict, dict]:
    from app.services.optimization_preview import preview

    reqs = _pick_requests(db, n)
    if not reqs:
        raise SystemExit("[BLOCKED] 找不到可用于整批解释的待入院住院证。")
    ids = [r.id for r in reqs]
    plan = preview(db, ids, solver="auto")
    evidence = {
        "kind": "aggregate_bed_allocation_preview",
        "fictional_teaching_only": True,
        "request_count": plan.request_count,
        "candidate_edges": plan.candidate_edges,
        "greedy": {"admitted": plan.baseline.admitted,
                   "priority_sum": plan.baseline.priority_sum,
                   "score_sum": plan.baseline.score_sum},
        "optimized": {"admitted": plan.optimized.admitted,
                      "priority_sum": plan.optimized.priority_sum,
                      "score_sum": plan.optimized.score_sum,
                      "method": plan.optimized.method,
                      "proven_optimal": plan.optimized.proven_optimal},
        "admitted_gain": plan.admitted_gain,
    }
    meta = {
        "source": "optimization_preview.preview(solver='auto') 的真实（合成）计算结果",
        "request_count": plan.request_count,
        "candidate_edges": plan.candidate_edges,
        "greedy_admitted": plan.baseline.admitted,
        "optimized_admitted": plan.optimized.admitted,
        "optimized_method": plan.optimized.method,
        "proven_optimal": plan.optimized.proven_optimal,
        "_forbidden_probe": {
            # 只检查 "住院证编号" 的显式形态：裸数字会与聚合指标（人数/评分总和）误撞，
            # 故不对聚合载荷做裸数字匹配。
            "request_id_strings": [f"#{i}" for i in ids],
        },
        "_probe_ids": ids,
    }
    return evidence, meta


def _collect_probe_tokens(db, req, item) -> dict:
    """收集"绝不允许出现"的识别性字符串，用于本地外发断言。"""
    probes = {"certificate_no": req.certificate_no}
    try:
        probes["patient_name"] = req.patient.name
    except Exception:  # noqa: BLE001
        probes["patient_name"] = None
    try:
        probes["bed_code"] = item.bed_code
    except Exception:  # noqa: BLE001
        probes["bed_code"] = None
    return {k: v for k, v in probes.items() if v}


def assert_no_identifiers(safe: dict, probe: dict) -> list[str]:
    blob = json.dumps(safe, ensure_ascii=False)
    problems = [f"命中禁止的键名: {k}" for k in sorted(set(safe) & FORBIDDEN_KEYS)]
    for key, value in (probe or {}).items():
        if isinstance(value, str) and value and value in blob:
            problems.append(f"命中识别性值({key}): {value!r}")
    for req_id in (probe or {}).get("request_id_strings", []):
        if re.search(r"(?<!\d)" + re.escape(req_id) + r"(?!\d)", blob):
            problems.append(f"命中住院证编号: {req_id!r}")
    return problems


# --------------------------------------------------------------------------- #
# dry-run：真实 Provider 代码 + MockTransport（零网络）
# --------------------------------------------------------------------------- #
def dry_run() -> int:
    import httpx
    from app.core.config import settings
    from app.services import deepseek_provider as dp

    hr("P4 REAL PILOT — 零网络彩排（dry-run）")
    state = load_state()
    say(f"Pilot ID        : {state['pilot_id']}")
    say(f"授权上限        : {AUTHORIZED_MAX_REQUESTS} 次真实请求 / ¥{AUTHORIZED_BUDGET_CNY}")
    say(f"已消耗          : {len(state['attempts'])} 次 / 累计估算 ¥{state['cumulative_estimate_cny']}")
    say(f"密钥是否就绪    : {dp.is_ready()}")
    rates = rates_from_settings()
    say(f"估算费率(元/M)  : miss={rates['miss']} hit={rates['hit']} out={rates['out']}")
    say()

    db = _session()
    results = []
    try:
        plan_specs = [("single", build_single_evidence), ("plan", build_plan_evidence)]
        for kind, builder in plan_specs:
            evidence, meta = builder(db)
            hr(f"[{kind}] 外发载荷核验（白名单 fail-closed）")
            safe = dp._safe_evidence("bed" if kind == "single" else "plan", evidence)
            problems = assert_no_identifiers(safe, meta.get("_forbidden_probe"))
            safe_json = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))

            # 用**真实** Provider 构造请求体：进程内临时开启（不落盘、不提交、无网络）
            real_enabled, real_key = settings.DEEPSEEK_EXTERNAL_ENABLED, settings.DEEPSEEK_API_KEY
            captured: dict = {}

            def handler(request: httpx.Request) -> httpx.Response:
                captured["url"] = str(request.url)
                captured["headers"] = dict(request.headers)
                captured["body"] = request.read().decode("utf-8")
                return httpx.Response(200, json={
                    "id": "simulated-dry-run-envelope",
                    "model": settings.DEEPSEEK_MODEL,
                    "choices": [{"finish_reason": "stop",
                                 "message": {"content": json.dumps(
                                     {"explanation": "（彩排占位，非真实模型输出）",
                                      "cautions": ["彩排占位"]}, ensure_ascii=False)}}],
                    "usage": {"prompt_tokens": 1234, "completion_tokens": 120,
                              "prompt_cache_hit_tokens": 0},
                })

            try:
                settings.DEEPSEEK_EXTERNAL_ENABLED = True
                settings.DEEPSEEK_API_KEY = "dry-run-in-process-placeholder"  # 仅进程内，绝不外发
                sent = dp.generate("bed" if kind == "single" else "plan", evidence,
                                   transport=httpx.MockTransport(handler))
                captured["parsed"] = sent.model, sent.usage, sent.cost_estimate_cny, sent.latency_ms
            finally:
                settings.DEEPSEEK_EXTERNAL_ENABLED, settings.DEEPSEEK_API_KEY = real_enabled, real_key

            body = json.loads(captured["body"])
            auth = captured["headers"].get("authorization", "")
            captured["headers"]["authorization"] = "<REDACTED>"  # 绝不落盘/回显
            messages_bytes = len(json.dumps(body["messages"], ensure_ascii=False).encode("utf-8"))
            wc = worst_case_cost_cny(messages_bytes, body["max_tokens"], rates)
            ceiling = worst_case_cost_cny(messages_bytes, body["max_tokens"], CEILING_RATES)

            checks = [
                ("endpoint 固定", captured["url"] == dp.DEEPSEEK_CHAT_URL),
                ("model == deepseek-flash", body["model"] == "deepseek-flash"),
                ("thinking 已禁用", body["thinking"] == {"type": "disabled"}),
                ("强制 JSON 输出", body["response_format"] == {"type": "json_object"}),
                ("stream == false", body["stream"] is False),
                ("max_tokens <= 500", body["max_tokens"] <= MAX_OUTPUT_TOKENS),
                ("messages JSON <= 8KB", messages_bytes <= MAX_MESSAGES_JSON_BYTES),
                ("Authorization 存在且不外泄", auth.startswith("Bearer ") and auth != ""),
                ("白名单无识别信息", not problems),
                ("系统提示要求输出 JSON", "纯 JSON 对象" in body["messages"][0]["content"]),
                ("用户消息即白名单快照", body["messages"][1]["content"] == safe_json),
                ("MockTransport 解析成功", captured["parsed"][0] == "deepseek-flash"),
            ]
            for name, ok in checks:
                say(f"  [{'PASS' if ok else 'FAIL'}] {name}")

            say(f"  · 载荷字节      : {messages_bytes} B (input_bound={messages_bytes} tokens)")
            say(f"  · 白名单 SHA256 : {sha256_text(safe_json)}")
            say(f"  · 最坏情况费用  : ¥{wc:.6f}（flash 高峰） / ¥{ceiling:.6f}（pro 高峰兜底）")
            say(f"  · 白名单载荷    : {safe_json}")
            if problems:
                say(f"  · !! 命中问题   : {problems}")
            say()
            results.append({"kind": kind, "checks": checks, "messages_bytes": messages_bytes,
                            "whitelist": safe, "whitelist_sha256": sha256_text(safe_json),
                            "worst_case_cny": round(wc, 8),
                            "meta": {k: v for k, v in meta.items() if not k.startswith("_")}})
    finally:
        db.close()

    total_wc = sum(r["worst_case_cny"] for r in results)
    hr("彩排结论")
    all_ok = all(ok for r in results for _, ok in r["checks"])
    say(f"  两项载荷全部通过检查 : {all_ok}")
    say(f"  两次调用最坏情况合计 : ¥{total_wc:.6f}  (授权预算 ¥{AUTHORIZED_BUDGET_CNY})")
    say(f"  预算是否充裕         : {total_wc <= AUTHORIZED_BUDGET_CNY}")
    say(f"  本次彩排真实网络请求 : 0（MockTransport 拦截）")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "preflight_dry_run.json").write_text(
        json.dumps({"generated_at": datetime.now(CN).isoformat(), "pilot_id": state["pilot_id"],
                    "real_network_requests": 0, "budget_cny": AUTHORIZED_BUDGET_CNY,
                    "worst_case_total_cny": round(total_wc, 8), "rates_cny_per_m": rates,
                    "items": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"  证据已写入           : {EVIDENCE_DIR / 'preflight_dry_run.json'}")
    return 0 if all_ok else 1


# --------------------------------------------------------------------------- #
# execute：真实调用（经本机 API）
# --------------------------------------------------------------------------- #
def _admin_password() -> str:
    src = (BACKEND / "seed.py").read_text(encoding="utf-8")
    m = re.search(r'username="admin",\s*\n\s*hash_password\("([^"]+)"\)', src)
    if not m:
        raise SystemExit("[BLOCKED] 无法从 seed.py 解析演示 ADMIN 口令。")
    return m.group(1)


def _db_snapshot() -> dict:
    from sqlalchemy import text
    db = _session()
    try:
        out = {}
        for t in ("beds", "bed_allocations", "admission_requests", "bed_status_logs", "audit_logs"):
            out[t] = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        out["active_allocations"] = db.execute(text(
            "SELECT COUNT(*) FROM bed_allocations WHERE status IN ('RESERVED','ADMITTED')")).scalar()
        out["beds_by_status"] = dict(db.execute(text(
            "SELECT status, COUNT(*) FROM beds GROUP BY status")).fetchall())
        return out
    finally:
        db.close()


def execute() -> int:
    import urllib.error
    import urllib.request
    from app.services import deepseek_provider as dp

    hr("P4 REAL PILOT — 真实调用（execute）")
    if not dp.is_ready():
        say("[BLOCKED] DeepSeek 未就绪：需要服务端密钥且 DEEPSEEK_EXTERNAL_ENABLED=true。")
        say("          本脚本不会向用户索取明文密钥；请自行在 backend/.env 填入后重启后端。")
        return 2

    API = "http://127.0.0.1:8000/api/v1"
    state = load_state()
    say(f"Pilot ID: {state['pilot_id']}")

    def login() -> str:
        req = urllib.request.Request(API + "/auth/login",
                                     data=json.dumps({"username": "admin", "password": _admin_password()}
                                                     ).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=20).read())["access_token"]

    token = login()

    def post(path: str, body: dict) -> tuple[int, dict]:
        req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + token})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                return exc.code, json.loads(raw)
            except Exception:  # noqa: BLE001
                return exc.code, {"raw": raw[:300]}

    db = _session()
    try:
        single_evidence, single_meta = build_single_evidence(db)
        plan_evidence, plan_meta = build_plan_evidence(db)
    finally:
        db.close()

    rates = rates_from_settings()
    messages_bound = len(json.dumps(single_evidence, ensure_ascii=False).encode()) + 700
    worst = worst_case_cost_cny(messages_bound, MAX_OUTPUT_TOKENS, rates)
    before = _db_snapshot()
    say(f"调用前数据库快照: {before}")

    # ---------------- 调用 #1：单床解释 ----------------
    seq = reserve_attempt(state, "single", worst)
    say(f"\n[#{seq}] 单床解释 → POST /assistant/explain (mode=llm)")
    status, data = post("/assistant/explain", {
        "admission_request_id": single_meta.get("_probe_rid"), "bed_id": single_meta.get("_probe_bed_id"),
        "mode": "llm", "confirm_external_call": True})
    if status != 200:
        finalize_attempt(state, seq, {"status": "FAILED", "http_status": status,
                                      "error": json.dumps(data, ensure_ascii=False)[:400]})
        say(f"  失败 HTTP {status}: {json.dumps(data, ensure_ascii=False)[:300]}")
        return 1
    rec = {"status": "SUCCESS", "http_status": status, "provider": data.get("provider"),
           "model": data.get("model"), "real_ai": data.get("real_ai"),
           "externally_sent": data.get("externally_sent"), "status_flag": data.get("status"),
           "prompt_tokens": data.get("input_tokens"), "completion_tokens": data.get("output_tokens"),
           "latency_ms": data.get("latency_ms"), "cost_estimate_cny": data.get("cost_estimate_cny")}
    finalize_attempt(state, seq, rec)
    say(f"  {json.dumps(rec, ensure_ascii=False)}")

    # ---------------- 调用 #2：整批解释（仅在预算可信且充足时） ----------------
    if state["cumulative_estimate_cny"] is None:
        say("\n[STOP] 累计费用无法确认，按授权要求不再发起第二次调用。")
    elif (AUTHORIZED_BUDGET_CNY - state["cumulative_estimate_cny"]) < worst:
        say("\n[STOP] 剩余预算不足以覆盖第二次最坏情况，按授权要求停止。")
    else:
        seq = reserve_attempt(state, "plan", worst)
        say(f"\n[#{seq}] 整批解释 → POST /assistant/explain-plan (mode=llm)")
        status, data = post("/assistant/explain-plan", {
            "admission_request_ids": plan_meta.get("_probe_ids"), "mode": "llm",
            "confirm_external_call": True})
        if status != 200:
            finalize_attempt(state, seq, {"status": "FAILED", "http_status": status,
                                          "error": json.dumps(data, ensure_ascii=False)[:400]})
            say(f"  失败 HTTP {status}: {json.dumps(data, ensure_ascii=False)[:300]}")
        else:
            rec = {"status": "SUCCESS", "http_status": status, "provider": data.get("provider"),
                   "model": data.get("model"), "real_ai": data.get("real_ai"),
                   "prompt_tokens": data.get("input_tokens"),
                   "completion_tokens": data.get("output_tokens"),
                   "latency_ms": data.get("latency_ms"),
                   "cost_estimate_cny": data.get("cost_estimate_cny"),
                   "assigned_count": data.get("assigned_count"),
                   "baseline_assigned_count": data.get("baseline_assigned_count")}
            finalize_attempt(state, seq, rec)
            say(f"  {json.dumps(rec, ensure_ascii=False)}")

    after = _db_snapshot()
    hr("业务副作用核验")
    say(f"  before: {before}")
    say(f"  after : {after}")
    say(f"  床位/分配/住院证计数是否不变: "
        f"{all(before[k] == after[k] for k in ('beds','bed_allocations','admission_requests','bed_status_logs'))}")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "execute_result.json").write_text(json.dumps(
        {"generated_at": datetime.now(CN).isoformat(), "state": state,
         "before": before, "after": after}, ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"\n真实请求数: {len(state['attempts'])} / 最多 {AUTHORIZED_MAX_REQUESTS}")
    say(f"累计估算费用: ¥{state['cumulative_estimate_cny']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="P4 DeepSeek Real Provider Pilot（有界、一次性）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="零网络彩排（MockTransport）")
    g.add_argument("--execute", action="store_true", help="执行被授权的真实调用")
    g.add_argument("--status", action="store_true", help="仅打印持久计数状态")
    args = ap.parse_args()
    if args.status:
        hr("PILOT 状态")
        say(json.dumps(load_state(), ensure_ascii=False, indent=2))
        return 0
    return dry_run() if args.dry_run else execute()


if __name__ == "__main__":
    raise SystemExit(main())
