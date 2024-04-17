"""

Revision ID: 0377_populate_org_brand_pools
Revises: 0376_email_branding_pools
Create Date: 2022-09-16 17:11:24.118619

"""

import textwrap

from alembic import op

revision = "0377_populate_org_brand_pools"
down_revision = "0376_email_branding_pools"


def upgrade():
    op.execute(
        textwrap.dedent(
            """
            INSERT INTO email_branding_to_organisation
            (organisation_id, email_branding_id)
            (SELECT organisation_id, email_branding_id FROM services
            JOIN service_email_branding
            ON services.id = service_id
            WHERE email_branding_id IS NOT NULL
            AND organisation_id IS NOT NULL
            AND count_as_live = true)
            ON CONFLICT DO NOTHING;
            """
        ).strip()
    )


def downgrade():
    pass
