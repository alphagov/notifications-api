"""

Revision ID: 0378_remove_doc_download_perm
Revises: 0377_populate_org_brand_pools
Create Date: 2022-10-12 11:55:28.906151

"""

from alembic import op

revision = "0378_remove_doc_download_perm"
down_revision = "0377_populate_org_brand_pools"


def upgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'document_download_verify_email'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'document_download_verify_email'")


def downgrade():
    pass
