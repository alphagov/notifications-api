"""

Revision ID: 0318_service_contact_list
Revises: 0317_uploads_for_all
Create Date: 2020-03-12 15:44:30.784031

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0318_service_contact_list'
down_revision = '0317_uploads_for_all'


def upgrade():
    op.create_table(
        'service_contact_list',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('original_file_name', sa.String(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('template_type', postgresql.ENUM(name='template_type', create_type=False), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_service_contact_list_created_by_id'), 'service_contact_list', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_service_contact_list_service_id'), 'service_contact_list', ['service_id'], unique=False)
    op.add_column('jobs', sa.Column('contact_list_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('jobs_contact_list_id_fkey', 'jobs', 'service_contact_list', ['contact_list_id'], ['id'])


def downgrade():
    op.drop_constraint('jobs_contact_list_id_fkey', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'contact_list_id')
    op.drop_index(op.f('ix_service_contact_list_service_id'), table_name='service_contact_list')
    op.drop_index(op.f('ix_service_contact_list_created_by_id'), table_name='service_contact_list')
    op.drop_table('service_contact_list')
