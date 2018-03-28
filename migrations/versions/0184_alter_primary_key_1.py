"""

Revision ID: 0184_alter_primary_key_1
Revises: 0183_alter_primary_key
Create Date: 2018-03-28 16:05:54.648645

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0184_alter_primary_key_1'
down_revision = '0183_alter_primary_key'


def upgrade():
    op.drop_constraint('ft_billing_pkey', 'ft_billing', type_='primary')

    op.create_primary_key('ft_billing_pkey', 'ft_billing', ['bst_date',
                                                            'template_id',
                                                            'service_id',
                                                            'rate_multiplier',
                                                            'provider',
                                                            'notification_type',
                                                            'international'])


def downgrade():
    op.drop_constraint('ft_billing_pkey', 'ft_billing', type_='primary')

    op.create_primary_key('ft_billing_pkey', 'ft_billing', ['bst_date',
                                                            'template_id',
                                                            'service_id',
                                                            'rate_multiplier',
                                                            'provider',
                                                            'notification_type'])
