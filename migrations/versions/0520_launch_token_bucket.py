"""
Create Date: 2025-09-01 01:01:01.000001
"""

from alembic import op

revision = '0520_launch_token_bucket'
down_revision = '0519_drop_n_hist_api_key_index'

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
            AND services.id NOT IN (
                '798e1041-4be3-4469-86b7-356c79e9ab65'
            )
        """
    )


def downgrade():
    op.execute(
        f"""
        DELETE from service_permissions where permission = '{TOKEN_BUCKET}'
        """
    )
