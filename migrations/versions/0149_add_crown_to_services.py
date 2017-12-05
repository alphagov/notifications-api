"""

Revision ID: 0149_add_crown_to_services
Revises: 0148_add_letters_as_pdf_svc_perm
Create Date: 2017-12-04 12:13:35.268712

"""
from alembic import op
import sqlalchemy as sa


revision = '0149_add_crown_to_services'
down_revision = '0148_add_letters_as_pdf_svc_perm'


def upgrade():
    op.add_column('services', sa.Column('crown', sa.Boolean(), nullable=True))
    op.execute("""
        update services set crown = True
        where organisation_type = 'central'
    """)
    op.execute("""
        update services set crown = True
        where organisation_type is null
    """)
    op.execute("""
        update services set crown = False
        where crown is null
    """)
    op.alter_column('services', 'crown', nullable=False)

    op.add_column('services_history', sa.Column('crown', sa.Boolean(), nullable=True))
    op.execute("""
        update services_history set crown = True
        where organisation_type = 'central'
    """)
    op.execute("""
        update services_history set crown = True
        where organisation_type is null
    """)
    op.execute("""
        update services_history set crown = False
        where crown is null
    """)
    op.alter_column('services_history', 'crown', nullable=False)


def downgrade():
    op.drop_column('services', 'crown')
    op.drop_column('services_history', 'crown')
