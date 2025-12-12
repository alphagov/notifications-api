"""
Create Date: 2025-12-03 12:38:18.704456
"""

from alembic import op
import sqlalchemy as sa

revision = '0541_service_confirm_sender_name'
down_revision = '0540_send_files_via_ui'


def upgrade():
    op.add_column('services', sa.Column('confirmed_email_sender_name', sa.Boolean(), nullable=True))
    op.add_column('services_history', sa.Column('confirmed_email_sender_name', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('services_history', 'confirmed_email_sender_name')
    op.drop_column('services', 'confirmed_email_sender_name')
