"""

Revision ID: 0277_consent_to_research_null
Revises: 0266_user_folder_perms_table
Create Date: 2019-03-01 13:47:15.720238

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0277_consent_to_research_null'
down_revision = '0266_user_folder_perms_table'


def upgrade():
    op.alter_column(
        'services',
        'consent_to_research',
        existing_type=sa.BOOLEAN(),
        nullable=True,
        server_default=sa.null(),
    )
    op.alter_column(
        'services_history',
        'consent_to_research',
        existing_type=sa.BOOLEAN(),
        nullable=True,
        server_default=sa.null(),
    )
    op.execute("""
        UPDATE
            services
        SET
            consent_to_research = null
    """)
    op.execute("""
        UPDATE
            services_history
        SET
            consent_to_research = null
    """)


def downgrade():
    op.execute("""
        UPDATE
            services
        SET
            consent_to_research = false
    """)
    op.execute("""
        UPDATE
            services_history
        SET
            consent_to_research = false
    """)
    op.alter_column(
        'services_history',
        'consent_to_research',
        existing_type=sa.BOOLEAN(),
        nullable=False,
        server_default=sa.false(),
    )
    op.alter_column(
        'services',
        'consent_to_research',
        existing_type=sa.BOOLEAN(),
        nullable=False,
        server_default=sa.false(),
    )
