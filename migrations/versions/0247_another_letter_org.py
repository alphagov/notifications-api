"""empty message

Revision ID: 0247_another_letter_org
Revises: 0246_notifications_index

"""

# revision identifiers, used by Alembic.
revision = '0247_another_letter_org'
down_revision = '0246_notifications_index'

from alembic import op


NEW_ORGANISATIONS = [
    ('520', 'Neath Port Talbot Council', 'npt'),
]


def upgrade():
    for numeric_id, name, filename in NEW_ORGANISATIONS:
        op.execute("""
            INSERT
                INTO dvla_organisation
                VALUES ('{}', '{}', '{}')
        """.format(numeric_id, name, filename))


def downgrade():
    for numeric_id, _, _ in NEW_ORGANISATIONS:
        op.execute("""
            DELETE
                FROM dvla_organisation
                WHERE id = '{}'
        """.format(numeric_id))
