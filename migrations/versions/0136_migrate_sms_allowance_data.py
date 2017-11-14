"""

Revision ID: 013_migrate_sms_allowance_data.py
Revises: 0135_stats_template_usage.py
Create Date: 2017-11-10 21:42:59.715203

"""
from datetime import datetime
from alembic import op
import uuid
from app.dao.date_util import get_current_financial_year_start_year


revision = '0136_migrate_sms_allowance_data'
down_revision = '0135_stats_template_usage'


def upgrade():
    current_year = get_current_financial_year_start_year()
    default_limit = 250000

    # Step 1: update the column free_sms_fragment_limit in service table if it is empty
    update_service_table = """
        UPDATE services SET free_sms_fragment_limit = {} where free_sms_fragment_limit is null
    """.format(default_limit)

    op.execute(update_service_table)

    # Step 2: insert at least one row for every service in current year if none exist for that service
    insert_row_if_not_exist = """
        INSERT INTO annual_billing 
        (id, service_id, financial_year_start, free_sms_fragment_limit, created_at, updated_at) 
         SELECT uuid_in(md5(random()::text || now()::text)::cstring), id, {}, {}, '{}', '{}' 
         FROM services WHERE id NOT IN 
        (select service_id from annual_billing)
    """.format(current_year, default_limit, datetime.utcnow(), datetime.utcnow())
    op.execute(insert_row_if_not_exist)

    # Step 3: copy the free_sms_fragment_limit data from the services table across to annual_billing table.
    update_sms_allowance = """
        UPDATE annual_billing SET free_sms_fragment_limit = services.free_sms_fragment_limit
        FROM services
        WHERE annual_billing.service_id = services.id
    """
    op.execute(update_sms_allowance)


def downgrade():
    print('There is no action for downgrading to the previous version.')