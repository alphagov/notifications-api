"""

Revision ID: 0252_letter_branding_table
Revises: 0251_another_letter_org
Create Date: 2019-01-17 15:45:33.242955

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0252_letter_branding_table'
down_revision = '0251_another_letter_org'


def upgrade():
    op.create_table('letter_branding',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('name', sa.String(length=255), nullable=False),
                    sa.Column('filename', sa.String(length=255), nullable=False),
                    sa.Column('domain', sa.Text(), nullable=True),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('domain'),
                    sa.UniqueConstraint('filename'),
                    sa.UniqueConstraint('name')
                    )
    op.create_table('service_letter_branding',
                    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('letter_branding_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.ForeignKeyConstraint(['letter_branding_id'], ['letter_branding.id'], ),
                    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
                    sa.PrimaryKeyConstraint('service_id')
                    )

    op.get_bind()


def downgrade():
    op.drop_table('service_letter_branding')
    op.drop_table('letter_branding')
