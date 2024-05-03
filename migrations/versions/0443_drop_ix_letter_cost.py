"""

Revision ID: 0443_drop_ix_letter_cost
Revises: 0442_add_new_service_permission
Create Date: 2023-09-17 15:17:58.545277

"""

from alembic import op


revision = "0443_drop_ix_letter_cost"
down_revision = "0442_add_new_service_permission"


def upgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_notifications_letter_despatch_cost_threshold",
            table_name="notifications_letter_despatch",
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_notifications_letter_despatch_cost_threshold",
            "notifications_letter_despatch",
            ["cost_threshold"],
            unique=False,
            postgresql_concurrently=True,
        )
