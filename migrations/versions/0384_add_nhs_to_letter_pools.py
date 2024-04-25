"""

Revision ID: 0384_add_nhs_to_letter_pools
Revises: 0383_webauthn_cred_logged_in_at
Create Date: 2022-11-17 13:59:56.978865

"""

from alembic import op

revision = "0384_add_nhs_to_letter_pools"
down_revision = "0383_webauthn_cred_logged_in_at"


def upgrade():
    op.execute(
        """
            INSERT INTO letter_branding_to_organisation
            (organisation_id, letter_branding_id)
            (SELECT id , '2cd354bb-6b85-eda3-c0ad-6b613150459f'
            FROM organisation WHERE organisation_type IN ('nhs_central', 'nhs_local', 'nhs_gp'))
            ON CONFLICT DO NOTHING;
            """
    )


def downgrade():
    pass
