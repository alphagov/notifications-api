"""

Revision ID: 0431_migrate_email_local_part
Revises: 0430_go_live_templates
Create Date: 2023-11-15 22:27:23.511256

"""

from alembic import op

revision = "0431_migrate_email_local_part"
down_revision = "0430_go_live_templates"


def upgrade():
    op.execute(
        """
        UPDATE services
        SET email_sender_local_part = normalised_service_name
        WHERE email_sender_local_part IS NULL
        """
    )
    op.execute(
        """
        UPDATE services_history
        SET email_sender_local_part = normalised_service_name
        WHERE email_sender_local_part IS NULL
        """
    )


def downgrade():
    pass
