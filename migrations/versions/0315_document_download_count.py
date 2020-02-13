"""

Revision ID: 0315_document_download_count
Revises: 0314_populate_email_access
Create Date: 2020-02-12 14:19:18.066425

"""
from alembic import op
import sqlalchemy as sa


revision = '0315_document_download_count'
down_revision = '0314_populate_email_access'


def upgrade():
    op.add_column('notifications', sa.Column('document_download_count', sa.Integer(), nullable=True))
    op.add_column('notification_history', sa.Column('document_download_count', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('notifications', 'document_download_count')
    op.drop_column('notification_history', 'document_download_count')
