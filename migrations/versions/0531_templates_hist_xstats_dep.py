"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0531_templates_hist_xstats_dep"
down_revision = "0530_template_folder_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_templates_history_service_id_sv_let_cct_id (dependencies) ON service_id, service_letter_contact_id FROM templates_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_history_service_id_let_att_id (dependencies) ON service_id, letter_attachment_id FROM templates_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_history_tpt_type_letter_lang (dependencies) ON template_type, letter_languages FROM templates_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_history_tpt_type_postage (dependencies) ON template_type, postage FROM templates_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_history_tpt_type_has_unsub_lnk (dependencies) ON template_type, has_unsubscribe_link FROM templates_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_templates_history_service_id_ctd_by_id (dependencies) ON service_id, created_by_id FROM templates_history"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_templates_history_service_id_sv_let_cct_id")
    op.execute("DROP STATISTICS st_dep_templates_history_service_id_let_att_id")
    op.execute("DROP STATISTICS st_dep_templates_history_tpt_type_letter_lang")
    op.execute("DROP STATISTICS st_dep_templates_history_tpt_type_postage")
    op.execute("DROP STATISTICS st_dep_templates_history_tpt_type_has_unsub_lnk")
    op.execute("DROP STATISTICS st_dep_templates_history_service_id_ctd_by_id")
