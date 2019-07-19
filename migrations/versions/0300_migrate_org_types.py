"""

Revision ID: 0300_migrate_org_types
Revises: 0299_org_types_table
Create Date: 2019-07-19 11:13:41.286472

"""
from alembic import op


revision = '0300_migrate_org_types'
down_revision = '0299_org_types_table'


def upgrade():
    op.execute("""
        UPDATE
            organisation
        SET
            organisation_type = 'nhs_local'
        FROM
            organisation_to_service, annual_billing
        WHERE
            organisation.organisation_type = 'nhs'
        AND
            annual_billing.service_id = organisation_to_service.service_id
        AND
            organisation_to_service.organisation_id = organisation.id
        AND
            annual_billing.free_sms_fragment_limit = 25000
    """)

    op.execute("""
        UPDATE
            services
        SET
            organisation_type = 'nhs_local'
        FROM
            annual_billing
        WHERE
            services.organisation_type = 'nhs'
        AND
            annual_billing.service_id = services.id
        AND
            annual_billing.free_sms_fragment_limit = 25000
    """)

    op.execute("""
        UPDATE
            organisation
        SET
            organisation_type = 'nhs_central'
        FROM
            organisation_to_service, annual_billing
        WHERE
            organisation.organisation_type = 'nhs'
        AND
            annual_billing.service_id = organisation_to_service.service_id
        AND
            organisation_to_service.organisation_id = organisation.id
        AND
            annual_billing.free_sms_fragment_limit = 250000
    """)

    op.execute("""
        UPDATE
            services
        SET
            organisation_type = 'nhs_central'
        FROM
            annual_billing
        WHERE
            services.organisation_type = 'nhs'
        AND
            annual_billing.service_id = services.id
        AND
            annual_billing.free_sms_fragment_limit = 250000
    """)


def downgrade():
    op.execute("""
        UPDATE
            organisation
        SET
            organisation_type = 'nhs'
        WHERE
            organisation_type = 'nhs_central'
    """)

    op.execute("""
        UPDATE
            services
        SET
            organisation_type = 'nhs'
        WHERE
            organisation_type = 'nhs_central'
    """)

    op.execute("""
        UPDATE
            organisation
        SET
            organisation_type = 'nhs'
        WHERE
            organisation_type = 'nhs_local'
    """)

    op.execute("""
        UPDATE
            services
        SET
            organisation_type = 'nhs'
        WHERE
            organisation_type = 'nhs_local'
    """)
