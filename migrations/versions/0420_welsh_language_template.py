"""

Revision ID: 0419_take_part_in_research
Revises: 0418_readd_null_constraint
Create Date: 2023-07-05 12:31:03.540011

"""
from alembic import op
import sqlalchemy as sa


revision = "0420_welsh_language_template"
down_revision = "0419_take_part_in_research"


def upgrade():

    op.add_column("templates", sa.Column("welsh_content", sa.Text()))
    op.add_column("templates", sa.Column("welsh_subject", sa.Text()))

    op.add_column("templates_history", sa.Column("welsh_content", sa.Text()))
    op.add_column("templates_history", sa.Column("welsh_subject", sa.Text()))


def downgrade():

    op.drop_column("templates", "welsh_content")
    op.drop_column("templates", "welsh_subject")

    op.drop_column("templates_history", "welsh_content")
    op.drop_column("templates_history", "welsh_subject")
