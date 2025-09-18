"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0529_templates_xstats_dep"
down_revision = "0528_report_requests_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_templates_tpt_type_postage (dependencies) ON template_type, postage FROM templates"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_service_id_sv_let_cct_id (dependencies) ON service_id, service_letter_contact_id FROM templates"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_service_id_ctd_by_id (dependencies) ON service_id, created_by_id FROM templates"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_tpt_type_letter_lang (dependencies) ON template_type, letter_languages FROM templates"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_service_id_let_att_id (dependencies) ON service_id, letter_attachment_id FROM templates"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_tpt_type_has_unsub_lnk (dependencies) ON template_type, has_unsubscribe_link FROM templates"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_templates_tpt_type_postage")
    op.execute("DROP STATISTICS st_dep_templates_service_id_sv_let_cct_id")
    op.execute("DROP STATISTICS st_dep_templates_service_id_ctd_by_id")
    op.execute("DROP STATISTICS st_dep_templates_tpt_type_letter_lang")
    op.execute("DROP STATISTICS st_dep_templates_service_id_let_att_id")
    op.execute("DROP STATISTICS st_dep_templates_tpt_type_has_unsub_lnk")
