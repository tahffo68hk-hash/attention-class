#!/usr/bin/env python
"""把 sql/init/00_create_database.sql 模板渲染为可执行 SQL。

口令来源（按优先级）：
  1. 环境变量 ``APP_DB_PASSWORD``
  2. ``backend/.env`` 中 ``DATABASE_URL`` 的口令段

取不到口令就**报错退出（exit 2）**，绝不回落到任何默认值 —— 避免"默认弱口令"
被写进数据库。渲染结果只输出到 stdout 或指定文件，**不会被提交**。

用法：
  python scripts/render_sql_init.py --print                 # 打印到 stdout
  python scripts/render_sql_init.py --out /tmp/init_db.sql  # 写入文件
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "sql" / "init" / "00_create_database.sql"
ENV_FILE = REPO / "backend" / ".env"
PLACEHOLDER = "__APP_DB_PASSWORD__"

try:  # 保证中文输出在 Windows 控制台可用
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def password_from_env_file() -> str | None:
    if not ENV_FILE.exists():
        return None
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(r"://[^:@/\s]+:([^@/\s]+)@", text)
    return m.group(1) if m else None


def resolve_password() -> str:
    pw = (os.environ.get("APP_DB_PASSWORD") or "").strip()
    if not pw:
        pw = (password_from_env_file() or "").strip()
    if not pw or pw == "CHANGE_ME_DB_PASSWORD" or pw.startswith("<"):
        print("[ERROR] 未取到真实口令：请设置环境变量 APP_DB_PASSWORD，"
              "或在 backend/.env 的 DATABASE_URL 中填入口令。", file=sys.stderr)
        raise SystemExit(2)
    return pw


def render() -> str:
    if not TEMPLATE.exists():
        print(f"[ERROR] 模板不存在：{TEMPLATE}", file=sys.stderr)
        raise SystemExit(2)
    sql = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in sql:
        print(f"[ERROR] 模板中未找到占位符 {PLACEHOLDER}", file=sys.stderr)
        raise SystemExit(2)
    return sql.replace(PLACEHOLDER, resolve_password())


def main() -> int:
    ap = argparse.ArgumentParser(description="渲染本地建库建号 SQL（口令来自环境，不入库）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--print", dest="to_stdout", action="store_true", help="输出到 stdout")
    g.add_argument("--out", type=Path, help="输出到指定文件（勿放在仓库内）")
    args = ap.parse_args()

    sql = render()
    if args.to_stdout:
        sys.stdout.write(sql)
        print("\n[OK] 已渲染（未落盘）", file=sys.stderr)
    else:
        args.out.write_text(sql, encoding="utf-8")
        print(f"[OK] 已渲染到 {args.out}（该文件含明文口令，请勿提交或长期留存）",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
