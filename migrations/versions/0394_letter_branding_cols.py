"""

Revision ID: 0394_letter_branding_cols
Revises: 0393_add_go_live_template
Create Date: 2023-01-05 14:12:47.272639

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0394_letter_branding_cols"
down_revision = "0393_add_go_live_template"


def upgrade():
    op.add_column("letter_branding", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("letter_branding", sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("letter_branding", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("letter_branding", sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("letter_branding_created_by_id_fkey", "letter_branding", "users", ["created_by_id"], ["id"])
    op.create_foreign_key("letter_branding_updated_by_id_fkey", "letter_branding", "users", ["updated_by_id"], ["id"])


def downgrade():
    op.drop_constraint("letter_branding_created_by_id_fkey", "letter_branding", type_="foreignkey")
    op.drop_constraint("letter_branding_updated_by_id_fkey", "letter_branding", type_="foreignkey")
    op.drop_column("letter_branding", "updated_by_id")
    op.drop_column("letter_branding", "updated_at")
    op.drop_column("letter_branding", "created_by_id")
    op.drop_column("letter_branding", "created_at")
