"""Display-only persistent slots plus soft retirement (no physical DELETE).

Revision ID: 20261015ed02
Revises: 9bca1026e001

Run against an isolated test database first. This migration backfills stable bed slots;
application code MUST NOT be deployed before the migration.
"""
from __future__ import annotations
import re
import sqlalchemy as sa
from alembic import op

revision='20261015ed02'
down_revision='9bca1026e001'
branch_labels=None
depends_on=None


def _natural(code: str):
    return tuple((1,int(p)) if p.isdigit() else (0,p.casefold()) for p in re.split(r'(\d+)',code))


def upgrade():
    op.add_column('beds',sa.Column('retired_at',sa.DateTime(),nullable=True))
    op.add_column('beds',sa.Column('retired_reason',sa.String(255),nullable=True))
    op.create_index('ix_beds_retired_at','beds',['retired_at'])
    op.create_table('bed_scene_slots',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('bed_id',sa.Integer(),sa.ForeignKey('beds.id',ondelete='RESTRICT'),nullable=False,unique=True),
        sa.Column('ward_id',sa.Integer(),sa.ForeignKey('wards.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('slot',sa.Integer(),nullable=False),
        sa.Column('rotation',sa.Integer(),nullable=False,server_default='0'),
        sa.CheckConstraint('slot >= 0',name='ck_bed_scene_slot_nonnegative'),
        sa.CheckConstraint('rotation IN (0,90,180,270)',name='ck_bed_scene_rotation'),
        sa.UniqueConstraint('ward_id','slot',name='uq_bed_scene_ward_slot'),
    )
    conn=op.get_bind()
    rows=conn.execute(sa.text('SELECT id,ward_id,code FROM beds')).all()
    grouped={}
    for bed_id,ward_id,code in rows:
        grouped.setdefault(ward_id,[]).append((bed_id,code))
    for ward_id,items in grouped.items():
        for slot,(bed_id,code) in enumerate(sorted(items,key=lambda b:(_natural(b[1]),b[0]))):
            conn.execute(sa.text('INSERT INTO bed_scene_slots (bed_id,ward_id,slot,rotation) VALUES (:b,:w,:s,0)'),
                         {'b':bed_id,'w':ward_id,'s':slot})


def downgrade():
    op.drop_table('bed_scene_slots')
    op.drop_index('ix_beds_retired_at',table_name='beds')
    op.drop_column('beds','retired_reason')
    op.drop_column('beds','retired_at')
