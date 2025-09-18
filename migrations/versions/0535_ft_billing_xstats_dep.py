"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0535_ft_billing_xstats_dep"
down_revision = "0534_api_keys_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_ft_billing_service_id_template_id (dependencies) ON service_id, template_id FROM ft_billing"
    )
    op.execute(
        "CREATE STATISTICS st_dep_ft_billing_ntfcn_type_template_id (dependencies) ON notification_type, template_id FROM ft_billing"
    )
    op.execute(
        "CREATE STATISTICS st_dep_ft_billing_ntfcn_type_provider (dependencies) ON notification_type, provider FROM ft_billing"
    )
    op.execute(
        "CREATE STATISTICS st_dep_ft_billing_ntfcn_type_intnl (dependencies) ON notification_type, international FROM ft_billing"
    )
    op.execute(
        "CREATE STATISTICS st_dep_ft_billing_ntfcn_type_postage (dependencies) ON notification_type, postage FROM ft_billing"
    )
    op.execute(
        "CREATE STATISTICS st_dep_ft_billing_provider_postage (dependencies) ON provider, postage FROM ft_billing"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_ft_billing_service_id_template_id")
    op.execute("DROP STATISTICS st_dep_ft_billing_ntfcn_type_template_id")
    op.execute("DROP STATISTICS st_dep_ft_billing_ntfcn_type_provider")
    op.execute("DROP STATISTICS st_dep_ft_billing_ntfcn_type_intnl")
    op.execute("DROP STATISTICS st_dep_ft_billing_ntfcn_type_postage")
    op.execute("DROP STATISTICS st_dep_ft_billing_provider_postage")
