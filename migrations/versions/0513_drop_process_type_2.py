"""
Create Date: 2025-08-12 11:11:11.111111
"""

from alembic import op
import sqlalchemy as sa

revision = "0513_drop_process_type_2"
down_revision = "0512_drop_process_type_1"


def upgrade():
    op.drop_column("templates", "process_type")


def downgrade():
    # Copied from migrations/0063_templates_process_type.py
    op.add_column("templates", sa.Column("process_type", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_templates_process_type"), "templates", ["process_type"], unique=False)
    op.create_foreign_key(
        "templates_process_type_fkey", "templates", "template_process_type", ["process_type"], ["name"]
    )
