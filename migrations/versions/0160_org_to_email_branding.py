"""

Revision ID: 0160_org_to_email_branding
Revises: 0159_add_historical_redact
Create Date: 2018-01-26 16:10:09.616551

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0160_org_to_email_branding'
down_revision = '0159_add_historical_redact'


def upgrade():
    op.create_table('email_branding',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('colour', sa.String(length=7), nullable=True),
        sa.Column('logo', sa.String(length=255), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.add_column('services', sa.Column('email_branding_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('services_history', sa.Column('email_branding_id', postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key(None, 'services', 'email_branding', ['email_branding_id'], ['id'])

    op.create_index(op.f('ix_services_email_branding_id'), 'services', ['email_branding_id'], unique=False)
    op.create_index(op.f('ix_services_history_email_branding_id'), 'services_history', ['email_branding_id'], unique=False)

    op.execute("""
        INSERT INTO email_branding (id, colour, logo, name)
        SELECT id, colour, logo, name
        FROM organisation
    """)


def downgrade():
    op.drop_column('services_history', 'email_branding_id')
    op.drop_column('services', 'email_branding_id')

    op.drop_table('email_branding')
