"""

Revision ID: 0292_give_users_folder_perms
Revises: 0291_remove_unused_index
Create Date: 2019-04-01 16:36:53.274394

"""
from alembic import op
from sqlalchemy.sql import text


revision = '0292_give_users_folder_perms'
down_revision = '0291_remove_unused_index'


def upgrade():
    op.execute(text(
        """INSERT INTO user_folder_permissions (user_id, template_folder_id, service_id)
        SELECT user_to_service.user_id, template_folder.id, user_to_service.service_id from user_to_service, template_folder
        WHERE template_folder.service_id = user_to_service.service_id
        ON CONFLICT do nothing"""
    ))


def downgrade():
    pass
