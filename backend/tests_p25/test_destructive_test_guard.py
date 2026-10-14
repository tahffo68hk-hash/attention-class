"""Verify the destructive MySQL fixture refuses non-test database names BEFORE connecting."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_mysql_suite_refuses_hospital_demo_database_at_import():
    backend = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env['TEST_DATABASE_URL'] = 'mysql+pymysql://user:synthetic@127.0.0.1:3307/hospital'
    # This must raise during module import, before any DB connection or DROP.
    proc = subprocess.run([sys.executable,'-c','import tests.conftest'], cwd=backend,
                          env=env, capture_output=True, text=True, timeout=10)
    assert proc.returncode != 0
    assert '破坏性 MySQL 测试只允许数据库名 hospital_test' in proc.stderr
