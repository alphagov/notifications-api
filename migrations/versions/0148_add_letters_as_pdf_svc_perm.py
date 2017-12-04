"""empty message

Revision ID: 0148_add_letters_as_pdf_svc_perm
Revises: 0147_drop_mapping_tables
Create Date: 2017-12-01 13:33:18.581320

"""

# revision identifiers, used by Alembic.
revision = '0148_add_letters_as_pdf_svc_perm'
down_revision = '0147_drop_mapping_tables'

from alembic import op


def upgrade():
    op.get_bind()
    op.execute("insert into service_permission_types values('letters_as_pdf')")


def downgrade():
    op.get_bind()
    op.execute("delete from service_permissions where permission = 'letters_as_pdf'")
    op.execute("delete from service_permission_types where name = 'letters_as_pdf'")
