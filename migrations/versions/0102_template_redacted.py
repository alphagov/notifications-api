"""empty message

Revision ID: db6d9d9f06bc
Revises: 0101_een_logo
Create Date: 2017-06-27 15:37:28.878359

"""

# revision identifiers, used by Alembic.
revision = 'db6d9d9f06bc'
down_revision = '0101_een_logo'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('template_redacted',
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('redact_personalisation', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('template_id')
    )
    op.create_index(op.f('ix_template_redacted_updated_by_id'), 'template_redacted', ['updated_by_id'], unique=False)


def downgrade():
    op.drop_table('template_redacted')
