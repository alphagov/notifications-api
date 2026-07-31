"""
Create Date: 2026-07-31 10:47:10.270170
"""

from alembic import op
import sqlalchemy as sa

revision = '0560_add_nhs_notify_org'
down_revision = '0559_set_nhs_notify_allowance'


organisation_id = '477f8870-af2b-4b81-9a2c-1fad12028919'

def upgrade():
    insert_sql = """
        INSERT INTO organisation
        (
            id,
            name,
            active,
            created_at,
            agreement_signed,
            crown,
            organisation_type,
            can_approve_own_go_live_requests
        )
        VALUES (
            :id,
            :name,
            :active,
            current_timestamp,
            :agreement_signed,
            :crown,
            :organisation_type,
            :can_approve_own_go_live_requests
        )
    """

    conn = op.get_bind()
    conn.execute(
        sa.text(insert_sql),
        {
            "id": organisation_id,
            "name": "NHS Notify",
            "active": True,
            "agreement_signed": True,
            "crown": False,
            "organisation_type": "nhs_notify",
            "can_approve_own_go_live_requests": True
        }
    )


def downgrade():
    update_service_remove_org_sql = """
        UPDATE services
        SET organisation_id = NULL, updated_at = current_timestamp
        WHERE organisation_id = :organisation_id
    """
    delete_sql = "DELETE FROM organisation WHERE id = :organisation_id"

    conn = op.get_bind()
    conn.execute(sa.text(update_service_remove_org_sql), {"organisation_id": organisation_id})
    conn.execute(sa.text(delete_sql), {"organisation_id": organisation_id})
