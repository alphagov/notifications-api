"""
Create Date: 2025-09-01 01:01:01.000001
"""

from alembic import op

revision = '0518_launch_token_bucket'
down_revision = '0517_remove_broadcast_sequence'

TOKEN_BUCKET = "token_bucket"

def upgrade():
    op.execute(
        f"""
        INSERT INTO
            service_permissions (service_id, permission, created_at)
        SELECT
            id, '{TOKEN_BUCKET}', now()
        FROM
            services
        WHERE
            NOT EXISTS (
                SELECT
                FROM
                    service_permissions
                WHERE
                    service_id = services.id and
                    permission = '{TOKEN_BUCKET}'
           )
        """
    )


def downgrade():
    op.execute(
        f"""
        DELETE from service_permissions where permission = '{TOKEN_BUCKET}'
        """
    )
