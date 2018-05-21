"""

Revision ID: 0191_ft_billing_pkey
Revises: 0190_another_letter_org
Create Date: 2018-05-21 14:24:27.229511

"""
from alembic import op

revision = '0191_ft_billing_pkey'
down_revision = '0190_another_letter_org'


def upgrade():
    op.get_bind()
    op.execute("ALTER TABLE ft_billing DROP CONSTRAINT ft_billing_pkey")
    sql = """ALTER TABLE ft_billing ADD CONSTRAINT 
    ft_billing_pkey PRIMARY KEY 
    (bst_date, template_id, service_id, rate_multiplier, provider, notification_type, international, rate)"""
    op.execute(sql)


def downgrade():
    op.get_bind()
    op.execute("ALTER TABLE ft_billing DROP CONSTRAINT ft_billing_pkey")
    sql = """ALTER TABLE ft_billing ADD CONSTRAINT 
    ft_billing_pkey PRIMARY KEY 
    (bst_date, template_id, service_id, rate_multiplier, provider, notification_type, international)"""
    op.execute(sql)