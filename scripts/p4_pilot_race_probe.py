#!/usr/bin/env python
"""Pilot 授权闸门并发探针（可复现的竞态验证工具）。

作用：用**真实子进程 + 文件栅栏**让 N 个实例同时进入
`reserve_attempt()` 的临界区，检查授权上限与预算闸门是否被突破。

用法：
  python scripts/p4_pilot_race_probe.py --workers 16
  python scripts/p4_pilot_race_probe.py --workers 8 --worst 0.3   # 测预算闸门

全程零网络、零数据库、零费用：只调用 `reserve_attempt()`。
状态文件写入系统临时目录，不触碰本机真实 Pilot 状态。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

RUNNER = pathlib.Path(__file__).resolve().parent / "p4_real_pilot.py"

WORKER = r'''
import importlib.util, os, pathlib, sys, time

spec = importlib.util.spec_from_file_location("p4runner", r"{runner}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ready = pathlib.Path(os.environ["RD"])
ready.mkdir(parents=True, exist_ok=True)
(ready / (os.environ["WID"] + ".ready")).write_text("1", encoding="utf-8")

deadline = time.monotonic() + 60
while not (ready / "GO").exists():
    if time.monotonic() > deadline:
        print("TIMEOUT"); sys.exit(9)
    time.sleep(0.001)

state = mod.load_state()
try:
    print("OK", mod.reserve_attempt(state, "single", float(os.environ["WORST"])))
except SystemExit:
    print("BLOCKED")
'''


def main() -> int:
    ap = argparse.ArgumentParser(description="Pilot 授权闸门并发探针")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--worst", type=float, default=0.001,
                    help="单次最坏情况费用估算（元），用于测预算闸门")
    ap.add_argument("--state", type=pathlib.Path, default=None)
    args = ap.parse_args()

    tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="p4race_"))
    state_path = args.state or (tmp_dir / "pilot_state.json")
    for p in (state_path, state_path.with_suffix(".lock")):
        p.unlink(missing_ok=True)

    helper = tmp_dir / "worker.py"
    helper.write_text(WORKER.replace("{runner}", str(RUNNER)), encoding="utf-8")
    ready = tmp_dir / "ready"
    ready.mkdir(parents=True, exist_ok=True)

    env0 = {**os.environ, "P4_PILOT_STATE_PATH": str(state_path),
            "RD": str(ready), "WORST": str(args.worst)}
    procs = [
        subprocess.Popen([sys.executable, str(helper)],
                         env={**env0, "WID": f"w{i}"},
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
        for i in range(args.workers)
    ]

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if len(list(ready.glob("w*.ready"))) >= args.workers:
            break
        time.sleep(0.005)
    (ready / "GO").write_text("1", encoding="utf-8")

    outcomes, failed = [], []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        lines = [l for l in (out or "").splitlines() if l.strip()]
        outcomes.append(lines[-1].strip() if lines else "")
        if proc.returncode != 0:
            failed.append((proc.returncode, (err or "").strip().splitlines()[-1:]))

    state = json.loads(state_path.read_text(encoding="utf-8"))
    ok = [o for o in outcomes if o.startswith("OK")]

    print(f"workers            = {args.workers}")
    print(f"单次最坏估算(元)   = {args.worst}")
    print(f"异常退出进程数     = {len(failed)}")
    for rc, tail in failed[:3]:
        print(f"   rc={rc} {tail}")
    print(f"声称成功占用数     = {len(ok)}  序号={sorted(ok)}")
    print(f"落盘 attempts      = {len(state['attempts'])}  (授权上限 2)")
    breached = len(ok) > 2 or len(state["attempts"]) > 2
    print(f"结论               = {'❌ 闸门被突破' if breached else '✅ 闸门未被突破'}")
    return 1 if breached else 0


if __name__ == "__main__":
    sys.exit(main())
