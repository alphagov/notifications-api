from alembic import op

revision = '0518_remove_token_bucket_perm'
down_revision = '0517_remove_broadcast_sequence'


def upgrade():
    op.execute("DELETE from service_permissions where permission = 'token_bucket'")
    op.execute("DELETE from service_permission_types where name = 'token_bucket'")


def downgrade():
    op.execute("INSERT INTO service_permission_types values ('token_bucket')")
