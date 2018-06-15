"""empty message

Revision ID: 0199_another_letter_org
Revises: 0198_add_caseworking_permission
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = '0199_another_letter_org'
down_revision = '0198_add_caseworking_permission'

from alembic import op


NEW_ORGANISATIONS = [
    ('009', 'HM Passport Office'),
]


def upgrade():
    for numeric_id, name in NEW_ORGANISATIONS:
        op.execute("""
            INSERT
                INTO dvla_organisation
                VALUES ('{}', '{}')
        """.format(numeric_id, name))


def downgrade():
    for numeric_id, _ in NEW_ORGANISATIONS:
        op.execute("""
            DELETE
                FROM dvla_organisation
                WHERE id = '{}'
        """.format(numeric_id))
