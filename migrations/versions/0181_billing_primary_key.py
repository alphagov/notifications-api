"""

Revision ID: 0181_billing_primary_key
Revises: 0180_another_letter_org
Create Date: 2018-03-21 13:41:26.203712

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0181_billing_primary_key'
down_revision = '0180_another_letter_org'


def upgrade():
    op.alter_column('ft_billing', 'service_id',
                    existing_type=postgresql.UUID(),
                    nullable=False)
    op.drop_constraint('ft_billing_pkey', 'ft_billing', type_='primary')

    op.create_primary_key('ft_billing_pkey', 'ft_billing', ['bst_date',
                                                            'template_id',
                                                            'rate_multiplier',
                                                            'provider',
                                                            'notification_type'])
    op.create_index(op.f('ix_ft_billing_template_id'), 'ft_billing', ['template_id'], unique=False)


def downgrade():
    op.alter_column('ft_billing', 'service_id',
                    existing_type=postgresql.UUID(),
                    nullable=True)

    op.drop_constraint('ft_billing_pkey', 'ft_billing', type_='primary')

    op.create_primary_key('ft_billing_pkey', 'ft_billing', ['bst_date',
                                                            'template_id',
                                                            'rate_multiplier',
                                                            'provider',
                                                            'international'])

    op.drop_index(op.f('ix_ft_billing_template_id'), table_name='ft_billing')
