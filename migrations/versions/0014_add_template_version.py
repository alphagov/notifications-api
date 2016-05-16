"""empty message

Revision ID: 0014_add_template_version
Revises: 0013_add_loadtest_client
Create Date: 2016-05-11 16:00:51.478012

"""

# revision identifiers, used by Alembic.
revision = '0014_add_template_version'
down_revision = '0013_add_loadtest_client'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.add_column('jobs', sa.Column('template_version', sa.Integer(), nullable=True))
    op.get_bind()
    op.execute('update jobs set template_version = (select version from templates where id = template_id)')
    op.add_column('notifications', sa.Column('template_version', sa.Integer(), nullable=True))
    op.execute('update notifications set template_version = (select version from templates where id = template_id)')
    op.alter_column('jobs', 'template_version', nullable=False)
    op.alter_column('notifications', 'template_version', nullable=False)

    # fix template_history where created_by_id is not set.
    query = "update templates_history set created_by_id = " \
            "         (select created_by_id from templates " \
            "           where templates.id = templates_history.id " \
            "           and templates.version = templates_history.version) " \
            "where templates_history.created_by_id is null"
    op.execute(query)


def downgrade():
    op.drop_column('notifications', 'template_version')
    op.drop_column('jobs', 'template_version')
