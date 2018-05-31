"""

Revision ID: 0196_service_contact_link
Revises: 0195_ft_notification_timestamps
Create Date: 2018-05-31 15:01:32.977620

"""
from alembic import op
import sqlalchemy as sa


revision = '0196_service_contact_link'
down_revision = '0195_ft_notification_timestamps'


def upgrade():
    op.add_column('services', sa.Column('contact_link', sa.String(length=255), nullable=True))
    op.add_column('services_history', sa.Column('contact_link', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('services_history', 'contact_link')
    op.drop_column('services', 'contact_link')
