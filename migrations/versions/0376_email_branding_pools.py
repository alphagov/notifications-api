"""

Revision ID: 0376_email_branding_pools
Revises: 0375_doc_download_verify_email
Create Date: 2022-08-22 13:47:31.180072

"""

import textwrap

from alembic import op

revision = "0376_email_branding_pools"
down_revision = "0375_doc_download_verify_email"


def upgrade():
    op.execute(
        textwrap.dedent(
            """
            INSERT INTO email_branding_to_organisation
            (organisation_id, email_branding_id)
            (SELECT id, email_branding_id FROM organisation WHERE email_branding_id IS NOT NULL)
            ON CONFLICT DO NOTHING;
            """
        ).strip()
    )


def downgrade():
    pass
