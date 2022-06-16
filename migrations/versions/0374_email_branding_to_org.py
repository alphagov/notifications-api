"""

Revision ID: 0374_email_branding_to_org
Revises: 0373_add_notifications_view
Create Date: 2022-06-16 11:05:30.754297

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0374_email_branding_to_org'
down_revision = '0373_add_notifications_view'


def upgrade():
    op.create_table(
        'email_branding_to_organisation',
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email_branding_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['email_branding_id'], ['email_branding.id'], ),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisation.id'], ),
        sa.PrimaryKeyConstraint('organisation_id', 'email_branding_id'),
        sa.UniqueConstraint('organisation_id', 'email_branding_id', name='uix_email_branding_to_organisation')
    )


def downgrade():
    op.drop_table('email_branding_to_organisation')
    # ### end Alembic commands ###
