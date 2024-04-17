"""

Revision ID: 0385_letter_branding_pools
Revises: 0384_add_nhs_to_letter_pools
Create Date: 2022-11-18 11:46:27.954516

"""

from alembic import op

revision = "0385_letter_branding_pools"
down_revision = "0384_add_nhs_to_letter_pools"


def upgrade():
    op.execute(
        """
            INSERT INTO letter_branding_to_organisation
            (organisation_id, letter_branding_id)
            (SELECT id, letter_branding_id FROM organisation WHERE letter_branding_id IS NOT NULL)
            ON CONFLICT DO NOTHING;
            """
    )


def downgrade():
    pass
