"""empty message

Revision ID: 0218_another_letter_org
Revises: 0217_default_email_branding

"""

# revision identifiers, used by Alembic.
revision = '0218_another_letter_org'
down_revision = '0217_default_email_branding'

from alembic import op


NEW_ORGANISATIONS = [
    ('511', 'NHS'),
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
