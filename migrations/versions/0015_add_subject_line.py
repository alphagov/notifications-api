"""empty message

Revision ID: 0015_add_subject_line
Revises: 0015_add_permissions
Create Date: 2016-02-18 09:43:29.282804

"""

# revision identifiers, used by Alembic.
revision = '0015_add_subject_line'
down_revision = '0015_add_permissions'

from alembic import op
import sqlalchemy as sa


def upgrade():
    pass
    op.add_column('templates', sa.Column('subject', sa.Text(), nullable=True))
    op.create_unique_constraint(None, 'templates', ['subject'])


def downgrade():
    pass
    op.drop_constraint(None, 'templates', type_='unique')
    op.drop_column('templates', 'subject')
