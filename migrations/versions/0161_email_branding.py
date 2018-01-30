"""

Revision ID: 0161_email_branding
Revises: 0160_another_letter_org
Create Date: 2018-01-30 15:35:12.016574

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0161_email_branding'
down_revision = '0160_another_letter_org'


def upgrade():
    op.create_table('email_branding',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('colour', sa.String(length=7), nullable=True),
        sa.Column('logo', sa.String(length=255), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('service_email_branding',
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('email_branding_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['email_branding_id'], ['email_branding.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.UniqueConstraint('service_id', name='uix_service_email_branding_one_per_service'),
        sa.PrimaryKeyConstraint('service_id')
    )
    op.execute("""
        INSERT INTO email_branding (id, colour, logo, name)
        SELECT id, colour, logo, name
        FROM organisation
    """)
    op.execute("""
        INSERT INTO service_email_branding (service_id, email_branding_id)
        SELECT id, organisation_id
        FROM services where organisation_id is not null
    """)


def downgrade():
    op.drop_table('service_email_branding')
    op.drop_table('email_branding')
