"""

Revision ID: 0217_add_govuk_brands
Revises: 0216_remove_colours
Create Date: 2018-08-23 11:48:00.800968

"""
from alembic import op
import uuid

revision = '0217_add_govuk_brands'
down_revision = '0216_remove_colours'

BRAND_NAMES = (
    'Animal & Plant Health Agency',
    'Attorney General\'s Office',
    'Cabinet Office',
    'Civil Service',
    'Civil Service Local',
    'Crown Commercial Service',
    'Department for Business, Energy & Industrial Strategy',
    'Department for Digital, Culture, Media & Sport',
    'Department for Education',
    'Department for Environment Food & Rural Affairs',
    'Department for Exiting the European Union',
    'Department for International  Development',
    'Department for International Trade',
    'Department for Transport',
    'Department for Work & Pensions',
    'Department of Health & Social Care',
    'Direct Debit',
    'Driver & Vehicle Standards Agency',
    'Education & Skills Funding Agency',
    'Environment Agency',
    'Food Standards Agency',
    'Foreign & Commonwealth Office',
    'GOV.UK Verify',
    'Government Actuary\'s Department',
    'Government Commercial Function',
    'Government Legal Department',
    'HM Courts & Tribunals Service',
    'HM Passport Office',
    'HM Revenue & Customs',
    'HM Treasury',
    'Home Office',
    'Marine Management Organisation',
    'Ministry of Defence',
    'Ministry of Housing, Communities & Local Government',
    'Ministry of Justice',
    'Northern Ireland Office',
    'Office of the Leader of the House of Commons',
    'Office of the Advocate General for Scotland',
    'Office of the Leader of the House of Lords',
    'Office of the Secretary of State for Scotland',
    'Office of the Secretary of State for Scotland',
    'Public Health England',
    'UK Export Finance',
    'UK Visas & Immigration',
)

NAME_WITH_GOVUK = '{} and GOV.UK'


def upgrade():

    for brand_name in BRAND_NAMES:
        op.execute("""
            INSERT INTO email_branding(
              id,
              colour,
              logo,
              name,
              text,
              brand_type
            )
            SELECT
              '{}'
              colour,
              logo,
              '{}',
              text,
              'both'
            FROM
              email_branding
            WHERE
              name = '{}'
        """.format(
            uuid.uuid4(),
            NAME_WITH_GOVUK.format(brand_name),
            brand_name,
        ))


def downgrade():

    for brand_name in BRAND_NAMES:
        op.execute("""
            DELETE FROM
                email_branding
            WHERE
                name = {}
        """.format(
            NAME_WITH_GOVUK.format(brand_name)
        ))
