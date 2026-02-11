"""

Create Date: 2025-02-10 17:07:41.828494
Revision ID: 0544_email_file_retention_fix
Revises: 0543_letter_rates_from_5_01_26

"""

revision = "0544_email_file_retention_fix"
down_revision = "0543_letter_rates_from_5_01_26"


from alembic import op
from sqlalchemy import text


def upgrade():
    conn = op.get_bind()
    conn.execute(
        text(
            """
            UPDATE
                template_email_files
            SET
                retention_period = 78
            WHERE
                retention_period > 78
            """
        )
    )


def downgrade():
    pass
