"""
Create Date: 2025-08-12 11:11:11.111111
"""

from alembic import op
import sqlalchemy as sa

revision = "0514_drop_process_type_3"
down_revision = "0513_drop_process_type_2"


def upgrade():
    op.drop_table("template_process_type")


def downgrade():
    # Copied from migrations/0063_templates_process_type.py
    op.create_table(
        "template_process_type",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.execute("INSERT INTO template_process_type VALUES ('normal'), ('priority')")
