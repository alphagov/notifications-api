"""empty message

Revision ID: 0182_add_upload_document_perm
Revises: 0181_billing_primary_key
Create Date: 2018-03-23 16:20:00

"""

# revision identifiers, used by Alembic.
revision = '0182_add_upload_document_perm'
down_revision = '0181_billing_primary_key'

from alembic import op


def upgrade():
    op.get_bind()
    op.execute("insert into service_permission_types values('upload_document')")


def downgrade():
    op.get_bind()
    op.execute("delete from service_permissions where permission = 'upload_document'")
    op.execute("delete from service_permission_types where name = 'upload_document'")
