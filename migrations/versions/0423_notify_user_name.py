"""

Revision ID: 0423_notify_user_name
Revises: 0422_letter_languages_constraint
Create Date: 2023-09-14 14:00:28.925639

"""

from alembic import op


revision = "0423_notify_user_name"
down_revision = "0422_letter_languages_constraint"


def upgrade():
    op.execute(
        """
        UPDATE users SET name = 'GOV.UK Notify' WHERE id = '6af522d0-2915-4e52-83a3-3690455a5fe6'
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE users SET name = 'Notify service user' WHERE id = '6af522d0-2915-4e52-83a3-3690455a5fe6'
        """
    )
