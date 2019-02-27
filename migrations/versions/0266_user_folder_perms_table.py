"""

Revision ID: 0266_user_folder_perms_table
Revises: 0265_add_confirm_edit_templates
Create Date: 2019-02-26 17:00:13.247321

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0266_user_folder_perms_table'
down_revision = '0265_add_confirm_edit_templates'


def upgrade():
    op.create_unique_constraint('ix_id_service_id', 'template_folder', ['id', 'service_id'])
    op.create_table('user_folder_permissions',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_folder_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['template_folder_id', 'service_id'], ['template_folder.id', 'template_folder.service_id'], ),
        sa.ForeignKeyConstraint(['user_id', 'service_id'], ['user_to_service.user_id', 'user_to_service.service_id'], ),
        sa.ForeignKeyConstraint(['template_folder_id'], ['template_folder.id'], ),
        sa.PrimaryKeyConstraint('user_id', 'template_folder_id', 'service_id'),
    )



def downgrade():
    op.drop_table('user_folder_permissions')
    op.drop_constraint('ix_id_service_id', 'template_folder', type_='unique')
