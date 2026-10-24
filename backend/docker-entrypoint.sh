#!/bin/sh
# 后端容器启动脚本：迁移 -> （空库时）写演示数据 -> 起服务
# 之所以放进脚本而不是直接写在 CMD 里：seed 只在空库执行，
# 避免每次 docker compose restart 都把演示数据清空重建。
set -e

echo "[entrypoint] 执行数据库迁移：alembic upgrade head"
python -m alembic upgrade head

if [ "${AUTO_SEED:-true}" = "true" ]; then
  python - <<'PY'
import sys

from sqlalchemy import text

from app.db.session import get_engine

with get_engine().connect() as conn:
    existing = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()

if existing:
    print(f"[entrypoint] users={existing}，跳过演示数据初始化（避免覆盖已有数据）")
    sys.exit(0)

print("[entrypoint] 检测到空库，写入演示数据")
import seed

seed.main()
PY
fi

echo "[entrypoint] 启动 uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
