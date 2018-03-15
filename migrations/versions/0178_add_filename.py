"""

Revision ID: 0178_add_filename
Revises: 0177_add_virus_scan_statuses
Create Date: 2018-03-14 16:15:01.886998

"""
from alembic import op
import sqlalchemy as sa


revision = '0178_add_filename'
down_revision = '0177_add_virus_scan_statuses'


def upgrade():
    # Deleting the data here is ok because a full migration from the files on s3 is coming.
    op.execute("DELETE FROM daily_sorted_letter")
    op.add_column('daily_sorted_letter', sa.Column('file_name', sa.String(), nullable=True))
    op.create_index(op.f('ix_daily_sorted_letter_file_name'), 'daily_sorted_letter', ['file_name'], unique=False)
    op.create_unique_constraint('uix_file_name_billing_day', 'daily_sorted_letter', ['file_name', 'billing_day'])
    op.drop_index('ix_daily_sorted_letter_billing_day', table_name='daily_sorted_letter')
    op.create_index(op.f('ix_daily_sorted_letter_billing_day'), 'daily_sorted_letter', ['billing_day'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_daily_sorted_letter_billing_day'), table_name='daily_sorted_letter')
    op.create_index('ix_daily_sorted_letter_billing_day', 'daily_sorted_letter', ['billing_day'], unique=True)
    op.drop_constraint('uix_file_name_billing_day', 'daily_sorted_letter', type_='unique')
    op.drop_index(op.f('ix_daily_sorted_letter_file_name'), table_name='daily_sorted_letter')
    op.drop_column('daily_sorted_letter', 'file_name')
