"""

Revision ID: 0188_add_ft_notification_status
Revises: 0187_another_letter_org
Create Date: 2018-05-03 10:10:41.824981

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0188_add_ft_notification_status'
down_revision = '0187_another_letter_org'


def upgrade():
    op.create_table('ft_notification_status',
    sa.Column('bst_date', sa.Date(), nullable=False),
    sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('notification_type', sa.Text(), nullable=False),
    sa.Column('key_type', sa.Text(), nullable=False),
    sa.Column('notification_status', sa.Text(), nullable=False),
    sa.Column('notification_count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('bst_date', 'template_id', 'service_id', 'job_id', 'notification_type', 'key_type', 'notification_status')
    )
    op.create_index(op.f('ix_ft_notification_status_bst_date'), 'ft_notification_status', ['bst_date'], unique=False)
    op.create_index(op.f('ix_ft_notification_status_job_id'), 'ft_notification_status', ['job_id'], unique=False)
    op.create_index(op.f('ix_ft_notification_status_service_id'), 'ft_notification_status', ['service_id'], unique=False)
    op.create_index(op.f('ix_ft_notification_status_template_id'), 'ft_notification_status', ['template_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_ft_notification_status_bst_date'), table_name='ft_notification_status')
    op.drop_index(op.f('ix_ft_notification_status_template_id'), table_name='ft_notification_status')
    op.drop_index(op.f('ix_ft_notification_status_service_id'), table_name='ft_notification_status')
    op.drop_index(op.f('ix_ft_notification_status_job_id'), table_name='ft_notification_status')
    op.drop_table('ft_notification_status')
