"""Isolated SQLite rehearsal for additive editor migration; NOT MySQL concurrency proof."""
import importlib.util
from pathlib import Path
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest

MIG=Path(__file__).resolve().parents[1]/'alembic'/'versions'/'20261015ed02_ward_bed_editor.py'


def test_migration_backfill_preserves_real_ids_and_unique_room_slots(tmp_path):
    eng=sa.create_engine(f'sqlite:///{tmp_path/"migration_only.db"}')
    with eng.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE wards (id INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('CREATE TABLE beds (id INTEGER PRIMARY KEY, ward_id INTEGER, code VARCHAR(32))')
        conn.exec_driver_sql('INSERT INTO wards (id) VALUES (1),(2)')
        conn.exec_driver_sql("INSERT INTO beds (id,ward_id,code) VALUES (10,1,'B-12'),(11,1,'B-2'),(12,1,'B-1'),(20,2,'A-1')")
        context=MigrationContext.configure(conn)
        spec=importlib.util.spec_from_file_location('migration_ward_editor',MIG)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.op=Operations(context)
        module.upgrade()
        ordered=conn.execute(sa.text('SELECT bed_id,ward_id,slot FROM bed_scene_slots ORDER BY ward_id,slot')).all()
        assert ordered==[(12,1,0),(11,1,1),(10,1,2),(20,2,0)]
        assert conn.execute(sa.text('SELECT COUNT(*) FROM beds')).scalar_one()==4
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(sa.text('INSERT INTO bed_scene_slots (bed_id,ward_id,slot,rotation) VALUES (20,1,1,0)'))
        assert 'retired_at' in {c['name'] for c in sa.inspect(conn).get_columns('beds')}
    eng.dispose()
