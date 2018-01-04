"""

Revision ID: ea1c2f80a50e
Revises: 0152_kill_service_free_fragments
Create Date: 2018-01-04 10:27:01.014640

"""
from alembic import op
import sqlalchemy as sa


revision = '0153_add_is_letter_contact_blank'
down_revision = '0152_kill_service_free_fragments'


def upgrade():
    op.add_column('templates', sa.Column('is_letter_contact_blank', sa.Boolean(), nullable=True))
    op.add_column('templates_history', sa.Column('is_letter_contact_blank', sa.Boolean(), nullable=True))
    op.execute("update templates set is_letter_contact_blank = false")
    op.execute("update templates_history set is_letter_contact_blank = false")
    op.alter_column("templates", "is_letter_contact_blank", nullable=False)
    op.alter_column("templates_history", "is_letter_contact_blank", nullable=False)

    op.create_check_constraint(
        "ck_templates_contact_block_is_blank",
        "templates",
        "Not(is_letter_contact_blank = True and service_letter_contact_id is not Null)"
    )
    op.create_check_constraint(
        "ck_templates_history_contact_block_is_blank",
        "templates_history",
        "Not(is_letter_contact_blank = True and service_letter_contact_id is not Null)"
    )


def downgrade():
    op.drop_column('templates_history', 'is_letter_contact_blank')
    op.drop_column('templates', 'is_letter_contact_blank')
