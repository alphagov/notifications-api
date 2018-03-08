"""

Revision ID: 0174_precompiled_pdf_rename
Revises: 0173_create_daily_sorted_letter
Create Date: 2018-03-06 17:09:56.619803

"""
from alembic import op


revision = '0174_precompiled_pdf_rename'
down_revision = '0173_create_daily_sorted_letter'


def upgrade():
    op.get_bind()
    op.execute(
        """
        update templates_history
        set name = 'Provided as PDF', subject = 'Provided as PDF'
        where templates_history.hidden = true and templates_history.name = 'Pre-compiled PDF'
        """
    )

    op.execute(
        """
        update templates
        set name = 'Provided as PDF', subject = 'Provided as PDF'
        where templates.hidden = true and templates.name = 'Pre-compiled PDF'
        """
    )


def downgrade():
    op.get_bind()
    op.execute(
        """
        update templates_history
        set name = 'Pre-compiled PDF', subject = 'Pre-compiled PDF'
        where templates_history.hidden = true and templates_history.name = 'Provided as PDF'
        """
    )

    op.execute(
        """
        update templates
        set name = 'Pre-compiled PDF', subject = 'Pre-compiled PDF'
        where templates.hidden = true and templates.name = 'Provided as PDF'
        """
    )
