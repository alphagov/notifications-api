"""

Revision ID: 0407_letter_attachments
Revises: 0406_1_april_2023_sms_rates
Create Date: 2023-03-09 08:45:00.990562

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0407_letter_attachments"
down_revision = "0406_1_april_2023_sms_rates"


def upgrade():
    op.create_table(
        "letter_attachment",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("archived_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("page_count", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["archived_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("templates", sa.Column("letter_attachment_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "templates_letter_attachment_id_fkey", "templates", "letter_attachment", ["letter_attachment_id"], ["id"]
    )
    op.add_column("templates_history", sa.Column("letter_attachment_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "templates_history_letter_attachment_id_fkey",
        "templates_history",
        "letter_attachment",
        ["letter_attachment_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_templates_letter_attachments", "templates", "template_type = 'letter' OR letter_attachment_id IS NULL"
    )
    op.create_check_constraint(
        "ck_templates_history_letter_attachments",
        "templates_history",
        "template_type = 'letter' OR letter_attachment_id IS NULL",
    )


def downgrade():
    op.drop_constraint("ck_templates_history_letter_attachments", "templates_history")
    op.drop_constraint("templates_history_letter_attachment_id_fkey", "templates_history", type_="foreignkey")
    op.drop_constraint("ck_templates_letter_attachments", "templates")
    op.drop_column("templates_history", "letter_attachment_id")
    op.drop_constraint("templates_letter_attachment_id_fkey", "templates", type_="foreignkey")
    op.drop_column("templates", "letter_attachment_id")
    op.drop_table("letter_attachment")
