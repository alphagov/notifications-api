"""empty message

Revision ID: 0020_template_history_fix
Revises: 0019_add_job_row_number
Create Date: 2016-05-20 15:15:03.850862

"""

# revision identifiers, used by Alembic.
revision = '0020_template_history_fix'
down_revision = '0019_add_job_row_number'

from alembic import op
import sqlalchemy as sa


def upgrade():
   op.get_bind()
   op.execute('update templates_history t set updated_at = (select updated_at from templates_history th where t.version = th.version -1 and t.id = th.id  and t.version != 1)')
   op.execute('update templates_history th set updated_at = (select t.updated_at from templates_history h, templates t where h.id = t.id and h.version = t.version and th.id = h.id) where (th.id, th.version) = (select t.id, t.version from templates t where t.id = th.id and t.version = th.version)')

def downgrade():
    pass
