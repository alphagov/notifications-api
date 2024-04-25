"""

Revision ID: 0245_archived_flag_jobs
Revises: 0244_another_letter_org
Create Date: 2018-11-22 16:32:01.105803

"""

import sqlalchemy as sa
from alembic import op

revision = "0245_archived_flag_jobs"
down_revision = "0244_another_letter_org"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("jobs", sa.Column("archived", sa.Boolean(), nullable=True))
    op.execute("update jobs set archived = false")
    op.alter_column("jobs", "archived", nullable=False, server_default=sa.false())

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("jobs", "archived")
    # ### end Alembic commands ###
