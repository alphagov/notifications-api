"""empty message

Revision ID: 0027_add_service_permission
Revises: 0023_drop_token
Create Date: 2016-02-25 12:41:29.112824

"""

# revision identifiers, used by Alembic.
revision = '0027_add_service_permission'
down_revision = '0026_add_sender'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('permission', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('service_id', 'user_id', 'permission', name='uix_service_user_permission')
    )
    op.create_index(op.f('ix_permissions_service_id'), 'permissions', ['service_id'], unique=False)
    op.create_index(op.f('ix_permissions_user_id'), 'permissions', ['user_id'], unique=False)
    op.drop_column('users', 'permissions')
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_permissions_user_id'), table_name='permissions')
    op.drop_index(op.f('ix_permissions_service_id'), table_name='permissions')
    op.drop_table('permissions')
    ### end Alembic commands ###
