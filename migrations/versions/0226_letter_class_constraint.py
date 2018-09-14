"""

Revision ID: 0226_letter_class_constraint
Revises: 0225_letter_class
Create Date: 2018-09-14 18:11:16.998693

"""
from alembic import op
import sqlalchemy as sa

revision = '0226_letter_class_constraint'
down_revision = '0225_letter_class'


def upgrade():
    op.execute("""
            update
                services
            set
                letter_class = 'second'
        """)
    op.execute("""
            update
                services_history
            set
                letter_class = 'second'
        """)
    op.create_check_constraint(
        'ck_services_letter_class',
        'services',
        "letter_class in ('second', 'first')"
    )
    op.alter_column('services_history', 'letter_class', nullable=False)
    op.alter_column('services', 'letter_class', nullable=False)


def downgrade():
    op.drop_constraint('ck_services_letter_class', 'services')
    op.alter_column('services_history', 'letter_class',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=True)
    op.alter_column('services', 'letter_class',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=True)
