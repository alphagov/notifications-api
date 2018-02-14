"""empty message

Revision ID: 0165_another_letter_org
Revises: 0164_add_organisation_to_service
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = '0165_another_letter_org'
down_revision = '0164_add_organisation_to_service'

from alembic import op


NEW_ORGANISATIONS = [
    ('502', 'Welsh Revenue Authority'),
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
