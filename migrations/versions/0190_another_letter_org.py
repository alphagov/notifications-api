"""empty message

Revision ID: 0190_another_letter_org
Revises: 0189_ft_billing_data_type
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = '0190_another_letter_org'
down_revision = '0189_ft_billing_data_type'

from alembic import op


NEW_ORGANISATIONS = [
    ('506', 'Tyne and Wear Fire and Rescue Service'),
    ('507', 'Thames Valley Police'),
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
