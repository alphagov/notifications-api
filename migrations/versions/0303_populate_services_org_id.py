"""

Revision ID: 0303_populate_services_org_id
Revises: 0302_add_org_id_to_services
Create Date: 2019-08-06 09:43:57.993510

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

revision = '0303_populate_services_org_id'
down_revision = '0302_add_org_id_to_services'


def upgrade():
    conn = op.get_bind()
    results = conn.execute("select service_id, organisation_id from organisation_to_service")
    org_to_service = results.fetchall()
    for x in org_to_service:
        sql = """
            UPDATE services
               SET organisation_id = :organisation_id
            WHERE id = :service_id
        """
        conn.execute(text(sql), service_id=str(x.service_id), organisation_id=str(x.organisation_id))
        history_sql = """
            UPDATE services_history
               SET organisation_id = :organisation_id
            WHERE id = :service_id
              AND version = (select max(version) from services_history sh2 where id = services_history.id); 
        """
        conn.execute(text(history_sql), service_id=str(x.service_id), organisation_id=str(x.organisation_id))


def downgrade():
    conn = op.get_bind()

    results = conn.execute("select id, organisation_id from services where organisation_id is not null")
    services = results.fetchall()
    results_2 = conn.execute("select service_id, organisation_id from organisation_to_service")
    org_to_service = results_2.fetchall()

    for x in services:
        os = [y for y in org_to_service if y.service_id == x.id]
        if len(os) == 1:
            update_sql = """
                UPDATE organisation_to_service
                   SET organisation_id = :organisation_id
                 WHERE service_id = :service_id
            """
            conn.execute(text(update_sql), service_id=str(x.id), organisation_id=str(x.organisation_id))
        elif len(os) == 0:
            insert_sql = """
                INSERT INTO organisation_to_service(service_id, organisation_id) VALUES(:service_id, :organisation_id)
            """
            conn.execute(text(insert_sql), service_id=str(x.id), organisation_id=str(x.organisation_id))
        else:
            raise Exception("should only have 1 row. Service_id {},  orgid: {}".format(x.id, x.organisation_id))
