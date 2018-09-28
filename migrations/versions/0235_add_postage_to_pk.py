"""

Revision ID: 0235_add_postage_to_pk
Revises: 0234_ft_billing_postage
Create Date: 2018-09-28 15:39:21.115358

"""
from alembic import op
import sqlalchemy as sa


revision = '0235_add_postage_to_pk'
down_revision = '0234_ft_billing_postage'


def upgrade():
    op.drop_constraint('ft_billing_pkey', 'ft_billing', type_='primary')
    op.create_primary_key('ft_billing_pkey', 'ft_billing', ['bst_date',
                                                            'template_id',
                                                            'service_id',
                                                            'notification_type',
                                                            'provider',
                                                            'rate_multiplier',
                                                            'international',
                                                            'rate',
                                                            'postage'])


def downgrade():
    op.drop_constraint('ft_billing_pkey', 'ft_billing', type_='primary')
    op.alter_column('ft_billing', 'postage', nullable=True)
    op.create_primary_key('ft_billing_pkey', 'ft_billing', ['bst_date',
                                                            'template_id',
                                                            'service_id',
                                                            'notification_type',
                                                            'provider',
                                                            'rate_multiplier',
                                                            'international',
                                                            'rate'])
