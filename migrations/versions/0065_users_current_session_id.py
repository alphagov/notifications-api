"""empty message

Revision ID: 0065_users_current_session_id
Revises: 0064_update_template_process
Create Date: 2017-02-17 11:48:40.669235

"""

# revision identifiers, used by Alembic.
revision = '0065_users_current_session_id'
down_revision = '0064_update_template_process'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.add_column('users', sa.Column('current_session_id', postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column('users', 'current_session_id')
