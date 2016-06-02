"""empty message

Revision ID: 0024_add_research_mode_defaults
Revises: 0023_add_research_mode
Create Date: 2016-05-31 11:11:45.979594

"""

# revision identifiers, used by Alembic.
revision = '0024_add_research_mode_defaults'
down_revision = '0023_add_research_mode'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute('update services set research_mode = false')
    op.execute('update services_history set research_mode = false')

def downgrade():
    pass