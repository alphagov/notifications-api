"""empty message

Revision ID: 0203_fix_old_incomplete_jobs
Revises: 0202_new_letter_pricing
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = '0203_fix_old_incomplete_jobs'
down_revision = '0202_new_letter_pricing'

from alembic import op


def upgrade():
    op.execute("""
        UPDATE
            jobs
        SET
            processing_started = created_at
        WHERE
            processing_started IS NULL
            AND
            job_status = 'in progress'
    """)


def downgrade():
    pass