"""empty message

Revision ID: 0016_add_email_from
Revises: 0015_add_subject_line
Create Date: 2016-02-18 11:25:37.915137

"""

# revision identifiers, used by Alembic.
revision = '0016_add_email_from'
down_revision = '0015_add_subject_line'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('services', sa.Column('email_from', sa.Text(), nullable=True))
    op.execute("UPDATE services SET email_from=name")


def downgrade():
    op.drop_column('services', 'email_from')
