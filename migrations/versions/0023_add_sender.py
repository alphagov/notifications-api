"""empty message

Revision ID: 0023_add_sender
Revises: 0022_add_processing_dates
Create Date: 2016-02-24 17:18:21.942772

"""

# revision identifiers, used by Alembic.
revision = '0023_add_sender'
down_revision = '0022_add_processing_dates'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('notifications', sa.Column('sent_by', sa.String(), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('notifications', 'sent_by')
    ### end Alembic commands ###
