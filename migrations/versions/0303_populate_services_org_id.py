"""

Revision ID: 0303_populate_services_org_id
Revises: 0302_add_org_id_to_services
Create Date: 2019-08-06 09:43:57.993510

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0303_populate_services_org_id'
down_revision = '0302_add_org_id_to_services'


def upgrade():
    sql = """
        UPDATE services
           SET organisation_id = (SELECT organisation_id from organisation_to_service 
                                  where organisation_to_service.service_id = services.id)
    """
    op.execute(sql)


def downgrade():
    sql = """
        UPDATE services
           SET organisation_id = null
    """
    op.execute(sql)
