"""

Revision ID: 0416_add_org_user_perms
Revises: 0415_org_invite_perms
Create Date: 2023-06-19 12:43:09.194732

"""

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy import text


revision = "0416_add_org_user_perms"
down_revision = "0415_org_invite_perms"


def upgrade():
    conn = op.get_bind()

    results = conn.execute(
        text(
            """
            SELECT user_id, organisation_id FROM user_to_organisation
            """
        )
    ).fetchall()

    for user_id, organisation_id in results:
        conn.execute(
            text(
                "INSERT INTO organisation_user_permissions "
                "(id, created_at, user_id, organisation_id, permission) "
                "VALUES (:id, :created_at, :user_id, :organisation_id, :permission)"
            ),
            id=uuid.uuid4(),
            created_at=datetime.utcnow(),
            organisation_id=organisation_id,
            user_id=user_id,
            permission="can_make_services_live",
        )


def downgrade():
    op.execute(text("DELETE FROM organisation_user_permissions WHERE permission = 'can_make_services_live'"))
