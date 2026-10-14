"""Pilot 执行器的**跨进程**授权闸门回归测试。

背景（真实缺陷，已修）：
`scripts/p4_real_pilot.py` 的 `reserve_attempt()` 原本是「读计数 → 校验上限/预算 →
占用额度 → 落盘」四步，彼此之间没有任何互斥。并发执行时各实例都读到同一份旧计数、
**同时通过**校验，于是：
  * 授权上限 2 次被绕过 —— N 个并发实例会真的发出 N 次真实付费请求；
  * 落盘计数只 +1（后写覆盖先写），事后审计也看不出超发；
  * `save_state()` 还共用同一 `.tmp` 文件名，并发时直接 PermissionError 崩溃。

本测试用**真实子进程 + 文件栅栏**让它们同时进入临界区，断言闸门守住。
全程零网络、零数据库、零费用：只调用 `reserve_attempt`，不触碰 `generate()`。
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

RUNNER = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "p4_real_pilot.py"

WORKER_SRC = r'''
import importlib.util, os, pathlib, sys, time

spec = importlib.util.spec_from_file_location("p4runner", r"{runner}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ready = pathlib.Path(os.environ["P4_TEST_READY_DIR"])
ready.mkdir(parents=True, exist_ok=True)
(ready / (os.environ["P4_TEST_WORKER_ID"] + ".ready")).write_text("1", encoding="utf-8")

deadline = time.monotonic() + 60
while not (ready / "GO").exists():
    if time.monotonic() > deadline:
        print("TIMEOUT")
        sys.exit(9)
    time.sleep(0.001)

state = mod.load_state()
try:
    seq = mod.reserve_attempt(state, "single", float(os.environ["P4_TEST_WORST"]))
    print("OK", seq)
except SystemExit:
    print("BLOCKED")
'''


def _run_concurrently(tmp_path: pathlib.Path, workers: int, worst: float):
    """并发跑 workers 个真实子进程，各自尝试占用一次授权额度。"""
    state_path = tmp_path / "pilot_state.json"
    lock_path = state_path.with_suffix(".lock")
    for p in (state_path, lock_path):
        p.unlink(missing_ok=True)

    helper = tmp_path / "worker.py"
    helper.write_text(WORKER_SRC.replace("{runner}", str(RUNNER)), encoding="utf-8")

    ready_dir = tmp_path / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)

    env = {**os.environ,
           "P4_PILOT_STATE_PATH": str(state_path),
           "P4_TEST_READY_DIR": str(ready_dir),
           "P4_TEST_WORST": str(worst)}
    procs = [
        subprocess.Popen([sys.executable, str(helper)], env={**env, "P4_TEST_WORKER_ID": f"w{i}"},
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
        for i in range(workers)
    ]

    # 等全部 worker 就绪再统一放行 —— 让它们几乎同时进入临界区
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if len(list(ready_dir.glob("w*.ready"))) >= workers:
            break
        time.sleep(0.005)
    (ready_dir / "GO").write_text("1", encoding="utf-8")

    outcomes, returncodes = [], []
    for proc in procs:
        out, _err = proc.communicate(timeout=120)
        returncodes.append(proc.returncode)
        lines = [l for l in (out or "").splitlines() if l.strip()]
        outcomes.append(lines[-1].strip() if lines else "")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    return outcomes, returncodes, state


def test_concurrent_reservations_cannot_exceed_authorized_limit(tmp_path):
    """16 个并发实例同时抢额度：只允许 2 次成功，且落盘计数必须正好 2。"""
    outcomes, returncodes, state = _run_concurrently(tmp_path, workers=16, worst=0.001)

    assert all(rc == 0 for rc in returncodes), f"有实例异常退出：{returncodes} / {outcomes}"
    ok = [o for o in outcomes if o.startswith("OK")]
    assert len(ok) == 2, f"授权上限被突破或过度拒绝：{outcomes}"
    assert sorted(ok) == ["OK 1", "OK 2"], f"序号异常：{ok}"
    assert len(state["attempts"]) == 2, f"落盘计数与授权上限不一致：{len(state['attempts'])}"
    assert state["cumulative_estimate_cny"] == 0.0


def test_concurrent_reservations_respect_budget_gate(tmp_path):
    """预算闸门：余量 ¥0.5、单次最坏 ¥0.3 → 并发下也只能放行 1 次。"""
    outcomes, returncodes, state = _run_concurrently(tmp_path, workers=8, worst=0.3)

    assert all(rc == 0 for rc in returncodes), f"有实例异常退出：{returncodes} / {outcomes}"
    ok = [o for o in outcomes if o.startswith("OK")]
    assert len(ok) == 1, f"预算闸门未按在途预留扣减：{outcomes}"
    assert len(state["attempts"]) == 1


def test_state_is_not_lost_when_writers_collide(tmp_path):
    """并发落盘不得丢更新：所有成功预留都必须出现在最终文件里。"""
    outcomes, _rc, state = _run_concurrently(tmp_path, workers=16, worst=0.001)
    ok = [o for o in outcomes if o.startswith("OK")]
    assert len(state["attempts"]) == len(ok), (
        f"落盘丢失更新：成功 {len(ok)} 次，文件里只有 {len(state['attempts'])} 条")


@pytest.mark.parametrize("workers", [1, 2])
def test_below_limit_all_reservations_succeed(tmp_path, workers):
    """低于上限时不得误拒：1~2 个实例应全部成功。"""
    outcomes, returncodes, state = _run_concurrently(tmp_path, workers=workers, worst=0.001)
    assert all(rc == 0 for rc in returncodes)
    assert all(o.startswith("OK") for o in outcomes), f"误拒：{outcomes}"
    assert len(state["attempts"]) == workers
