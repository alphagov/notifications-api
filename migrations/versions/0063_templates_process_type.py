"""empty message

Revision ID: 0063_templates_process_type
Revises: 0062_provider_details_history
Create Date: 2017-01-10 15:39:30.909308

"""

# revision identifiers, used by Alembic.
revision = '0063_templates_process_type'
down_revision = '0062_provider_details_history'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('template_process_type',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )
    op.execute("INSERT INTO template_process_type VALUES ('normal'), ('priority')")
    op.add_column('templates', sa.Column('process_type', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_templates_process_type'), 'templates', ['process_type'], unique=False)
    op.create_foreign_key('templates_history_process_type_fkey', 'templates', 'template_process_type', ['process_type'], ['name'])
    op.add_column('templates_history', sa.Column('process_type', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_templates_history_process_type'), 'templates_history', ['process_type'], unique=False)
    op.create_foreign_key('templates_process_type_fkey', 'templates_history', 'template_process_type', ['process_type'], ['name'])


def downgrade():
    op.drop_constraint('templates_history_process_type_fkey', 'templates_history', type_='foreignkey')
    op.drop_index(op.f('ix_templates_history_process_type'), table_name='templates_history')
    op.drop_column('templates_history', 'process_type')
    op.drop_constraint('templates_process_type_fkey', 'templates', type_='foreignkey')
    op.drop_index(op.f('ix_templates_process_type'), table_name='templates')
    op.drop_column('templates', 'process_type')
    op.drop_table('template_process_type')
