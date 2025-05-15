"""
Create Date: 2025-04-17 15:09:47.846941
"""
from alembic import op

revision = '0498_join_a_service_for_all'
down_revision = '0497_add_economy_letter_flag'


def upgrade():
    op.execute(
        """
        INSERT INTO
            organisation_permissions (id, permission, organisation_id, created_at)
        SELECT
            gen_random_uuid(), '{permission}', id, now()
        FROM
            organisation
        WHERE
            NOT EXISTS (
                SELECT
                FROM
                    organisation_permissions
                WHERE
                    organisation_id = organisation.id and
                    permission = '{permission}'
           )
    """.format(
            permission="can_ask_to_join_a_service"
        )
    )

def downgrade():
    # We can't tell which organisations already had the permission, so if reversing this migration
    # we just remove the permission from allg
    op.execute("DELETE FROM organisation_permissions WHERE permission = 'can_ask_to_join_a_service'")
