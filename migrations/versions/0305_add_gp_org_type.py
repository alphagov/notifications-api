import os

"""

Revision ID: 0305_add_gp_org_type
Revises: 0304_remove_org_to_service
Create Date: 2019-07-24 16:18:27.467361

"""
from alembic import op


revision = '0305_add_gp_org_type'
down_revision = '0304_remove_org_to_service'
GP_ORG_TYPE_NAME = 'nhs_gp'


def upgrade():
    op.execute("""
        INSERT INTO
            organisation_types
            (name, is_crown, annual_free_sms_fragment_limit)
        VALUES
            ('{}', false, 25000)
    """.format(GP_ORG_TYPE_NAME))


def downgrade():
    op.execute("""
        UPDATE
            organisation
        SET
            organisation_type = 'nhs_local'
        WHERE
            organisation_type = '{}'
    """.format(GP_ORG_TYPE_NAME))
    op.execute("""
        DELETE FROM
            organisation_types
        WHERE
            name = '{}'
    """.format(GP_ORG_TYPE_NAME))
