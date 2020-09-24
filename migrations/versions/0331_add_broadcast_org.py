"""

Revision ID: 0331_add_broadcast_org
Revises: 0330_broadcast_invite_email
Create Date: 2020-09-23 10:11:01.094412

"""
from alembic import op
import sqlalchemy as sa
import os

revision = '0331_add_broadcast_org'
down_revision = '0330_broadcast_invite_email'

environment = os.environ['NOTIFY_ENVIRONMENT']

organisation_id = '38e4bf69-93b0-445d-acee-53ea53fe02df'


def upgrade():
    # we've already done this manually on production
    if environment != "production":
        insert_sql = """
            INSERT INTO organisation
            (
                id,
                name,
                active,
                created_at,
                agreement_signed,
                crown,
                organisation_type
            )
            VALUES (
                :id,
                :name,
                :active,
                current_timestamp,
                :agreement_signed,
                :crown,
                :organisation_type
            )
        """
        update_service_set_broadcast_org_sql = """
        UPDATE services
        SET organisation_id = :organisation_id
        WHERE id in (
            SELECT service_id
            FROM service_permissions
            WHERE permission = 'broadcast'
        )
        """
        conn = op.get_bind()
        conn.execute(
            sa.text(insert_sql),
            id=organisation_id,
            name=f'Broadcast Services ({environment})',
            active=True,
            agreement_signed=None,
            crown=None,
            organisation_type='central',
        )
        conn.execute(
            sa.text(update_service_set_broadcast_org_sql),
            organisation_id=organisation_id
        )


def downgrade():
    update_service_remove_org_sql = """
        UPDATE services
        SET organisation_id = NULL, updated_at = current_timestamp
        WHERE organisation_id = :organisation_id
    """
    delete_sql = """
        DELETE FROM organisation
        WHERE id = :organisation_id
    """
    conn = op.get_bind()
    conn.execute(sa.text(update_service_remove_org_sql), organisation_id=organisation_id)
    conn.execute(sa.text(delete_sql), organisation_id=organisation_id)
