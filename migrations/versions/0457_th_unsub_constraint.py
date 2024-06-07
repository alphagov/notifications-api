"""
Create Date: 2024-06-07 10:37:51.851999
"""

from alembic import op

revision = "0457_th_unsub_constraint"
down_revision = "0456_t_unsub_constraint"


def upgrade():
    # acquires access exclusive, but only very briefly as the not_valid stops it doing a full table scan
    op.create_check_constraint(
        "ck_templates_history_non_email_has_unsubscribe_false",
        "templates_history",
        "template_type = 'email' OR has_unsubscribe_link IS false",
        postgresql_not_valid=True,
    )


def downgrade():
    op.drop_constraint("ck_templates_history_non_email_has_unsubscribe_false", "templates_history")
