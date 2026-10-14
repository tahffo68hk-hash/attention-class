"""M1: one active allocation per admission request, plus durable idempotency.

Revision ID: 9bca1026e001
Revises: 573c803013d2

Requires MySQL 8.0+ for generated STORED column and indexed nullable values.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '9bca1026e001'
down_revision = '573c803013d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicated = bind.execute(sa.text(
        "SELECT admission_request_id, COUNT(*) AS n FROM bed_allocations "
        "WHERE status IN ('RESERVED', 'ADMITTED') "
        "GROUP BY admission_request_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicated:
        raise RuntimeError(
            '存在单住院证多个活动分配，迁移已停止；请先人工核对并修复，'
            f'admission_request_id={duplicated[0]}, count={duplicated[1]}'
        )

    op.add_column(
        'bed_allocations',
        sa.Column(
            'active_request_id', sa.Integer(),
            sa.Computed(
                "CASE WHEN status IN ('RESERVED', 'ADMITTED') "
                "THEN admission_request_id ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
            comment='活动分配的申请 ID（由数据库生成，不允许应用写入）',
        ),
    )
    op.create_unique_constraint(
        'uq_bed_allocations_active_request_id',
        'bed_allocations', ['active_request_id'],
    )
    op.create_table(
        'allocation_idempotency',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_key', sa.String(length=128), nullable=False),
        sa.Column('payload_sha256', sa.String(length=64), nullable=False),
        sa.Column('allocation_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_key', name='uq_allocation_idempotency_key'),
        sa.ForeignKeyConstraint(['allocation_id'], ['bed_allocations.id'], ondelete='RESTRICT'),
    )


def downgrade() -> None:
    op.drop_table('allocation_idempotency')
    op.drop_constraint('uq_bed_allocations_active_request_id', 'bed_allocations', type_='unique')
    op.drop_column('bed_allocations', 'active_request_id')
