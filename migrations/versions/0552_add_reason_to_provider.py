"""
Create Date: 2026-06-09 12:50:30.454463
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = '0552_add_reason_to_provider'
down_revision = '0551_drop_ntfcns_failed_idx'


def upgrade():
    conn = op.get_bind()
    conn.execute(text("SET lock_timeout = '60s'"))
    conn.execute(text("SET statement_timeout = '60s'"))
    op.add_column('provider_details', sa.Column('reason', sa.String(), nullable=True))
    op.add_column('provider_details_history', sa.Column('reason', sa.String(), nullable=True))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("SET lock_timeout = '60s'"))
    conn.execute(text("SET statement_timeout = '60s'"))
    op.drop_column('provider_details', 'reason')
    op.drop_column('provider_details_history', 'reason')
