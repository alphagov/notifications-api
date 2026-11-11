"""
Add active column to letter_branding

Revision ID: 0588_active_letter_branding
Revises: 0587_replica_index_notif_history
Create Date: 2026-11-03 11:16:39

"""

from alembic import op
import sqlalchemy as sa


revision = "0588_active_letter_branding"
down_revision = "0587_replica_index_notif_history"


def upgrade():
    op.add_column("letter_branding", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("letter_branding", "active")
