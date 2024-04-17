"""

Revision ID: 0411_contact_list_idx
Revises: 0410_drop_unused_allowance
Create Date: 2023-05-11 15:00:59.123645

"""

from alembic import op


revision = "0411_contact_list_idx"
down_revision = "0410_drop_unused_allowance"


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            op.f("ix_jobs_contact_list_id"), "jobs", ["contact_list_id"], unique=False, postgresql_concurrently=True
        )


def downgrade():
    op.drop_index(op.f("ix_jobs_contact_list_id"), table_name="jobs")
