"""

Revision ID: 0375_doc_download_verify_email
Revises: 0374_email_branding_to_org
Create Date: 2020-09-13 28:17:17.110495

"""

import sqlalchemy as sa
from alembic import op

revision = "0375_doc_download_verify_email"
down_revision = "0374_email_branding_to_org"


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('document_download_verify_email')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'document_download_verify_email'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'document_download_verify_email'")
