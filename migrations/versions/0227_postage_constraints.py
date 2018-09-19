"""
Revision ID: 0227_postage_constraints
Revises: 0226_service_postage
Create Date: 2018-09-13 16:23:59.168877
"""
from alembic import op
import sqlalchemy as sa

revision = '0227_postage_constraints'
down_revision = '0226_service_postage'


def upgrade():
    op.execute("""
            update
                services
            set
                postage = 'second'
        """)

    op.create_check_constraint(
        'ck_services_postage',
        'services',
        "postage in ('second', 'first')"
    )
    op.alter_column('services', 'postage', nullable=False)


def downgrade():
    op.drop_constraint('ck_services_postage', 'services')
    op.alter_column('services', 'postage',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=True)
