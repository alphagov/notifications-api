"""

Revision ID: 0382_nhs_letter_branding_id
Revises: 0381_letter_branding_to_org
Create Date: 2022-11-15 07:57:49.060820

"""

import os

from alembic import op

revision = "0382_nhs_letter_branding_id"
down_revision = "0381_letter_branding_to_org"

environment = os.environ["NOTIFY_ENVIRONMENT"]


def upgrade():
    if environment not in ["live", "production"]:
        op.execute(
            """
            DELETE FROM service_letter_branding
            WHERE letter_branding_id in (
                SELECT id
                FROM letter_branding
                WHERE name = 'NHS'
            )
        """
        )

        op.execute(
            """
            DELETE FROM letter_branding_to_organisation
            WHERE letter_branding_id in (
                SELECT id
                FROM letter_branding
                WHERE name = 'NHS'
            )
        """
        )

        op.execute(
            """
            UPDATE organisation SET letter_branding_id = null
            WHERE letter_branding_id in(
                SELECT id
                FROM letter_branding
                WHERE name = 'NHS'
            )
        """
        )

        op.execute(
            """
            DELETE FROM letter_branding WHERE name = 'NHS'
        """
        )

        op.execute(
            """
            INSERT INTO letter_branding (
                id, name, filename
            )
            VALUES (
                '2cd354bb-6b85-eda3-c0ad-6b613150459f',
                'NHS',
                'nhs'
            )
        """
        )


def downgrade():
    """
    No downgrade step since this is not fully reversible, but won't be run in production.
    """
