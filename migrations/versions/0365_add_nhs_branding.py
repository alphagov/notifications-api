"""

Revision ID: 0365_add_nhs_branding
Revises: 0364_drop_old_column
Create Date: 2022-02-17 16:31:21.415065

"""

import os

from alembic import op

revision = "0365_add_nhs_branding"
down_revision = "0364_drop_old_column"

environment = os.environ["NOTIFY_ENVIRONMENT"]


def upgrade():
    if environment not in ["live", "production"]:
        op.execute(
            """
            DELETE FROM service_email_branding
            WHERE email_branding_id in (
                SELECT id
                FROM email_branding
                WHERE name = 'NHS'
            )
        """
        )

        op.execute(
            """
            UPDATE organisation SET email_branding_id = null
            WHERE email_branding_id in(
                SELECT id
                FROM email_branding
                WHERE name = 'NHS'
            )
        """
        )

        op.execute(
            """
            DELETE FROM email_branding WHERE name = 'NHS'
        """
        )

        op.execute(
            """
            INSERT INTO email_branding (
                id, logo, name, brand_type
            )
            VALUES (
                'a7dc4e56-660b-4db7-8cff-12c37b12b5ea',
                '1ac6f483-3105-4c9e-9017-dd7fb2752c44-nhs-blue_x2.png',
                'NHS',
                'org'
            )
        """
        )


def downgrade():
    """
    No downgrade step since this is not fully reversible, but won't be run in production.
    """
