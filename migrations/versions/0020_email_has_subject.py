"""empty message

Revision ID: 0020_email_has_subject
Revises: 0019_unique_servicename
Create Date: 2016-02-18 11:45:29.102891

"""

# revision identifiers, used by Alembic.
revision = '0020_email_has_subject'
down_revision = '0019_unique_servicename'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_check_constraint(
        "ch_email_template_has_subject",
        "templates",
        "((template_type='email' and subject is not null) or (template_type!='email' and subject is null))"
    )


def downgrade():
    op.drop_constraint('ch_email_template_has_subject', 'templates', type_='check')
