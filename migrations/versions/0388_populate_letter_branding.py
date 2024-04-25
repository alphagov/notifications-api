"""

Revision ID: 0388_populate_letter_branding
Revises: 0387_migrate_alt_text
Create Date: 2022-11-24 14:04:41.456302

"""

from alembic import op

revision = "0388_populate_letter_branding"
down_revision = "0387_migrate_alt_text"


def upgrade():
    op.execute(
        """
        INSERT INTO letter_branding_to_organisation
        (organisation_id, letter_branding_id)
        (SELECT organisation_id, letter_branding_id FROM services
        JOIN service_letter_branding
        ON services.id = service_id
        WHERE letter_branding_id IS NOT NULL
        AND organisation_id IS NOT NULL
        AND count_as_live = true)
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade():
    pass
