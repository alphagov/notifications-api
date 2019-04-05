"""empty message

Revision ID: 0285_default_org_branding
Revises: 0284_0283_retry
Create Date: 2016-10-25 17:37:27.660723

"""

# revision identifiers, used by Alembic.
revision = '0285_default_org_branding'
down_revision = '0284_0283_retry'

from alembic import op
import sqlalchemy as sa


BRANDING_TABLES = ('email_branding', 'letter_branding')


def upgrade():
    for branding in BRANDING_TABLES:
        op.execute("""
            UPDATE
                organisation
            SET
                {branding}_id = {branding}.id
            FROM
                {branding}
            WHERE
                {branding}.domain in (
                    SELECT
                        domain
                    FROM
                        domain
                    WHERE
                        domain.organisation_id = organisation.id
                )
        """.format(branding=branding))

def downgrade():
    for branding in BRANDING_TABLES:
        op.execute("""
            UPDATE
                organisation
            SET
                {branding}_id = null
        """.format(branding=branding))
