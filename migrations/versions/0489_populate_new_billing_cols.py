from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0489_populate_new_billing_cols"
down_revision = "0488_add_annual_billing_columns"


def upgrade():
    # update billing for services we have set to a non-zero value to be has_custom=True
    op.execute(
        """
        UPDATE annual_billing
        SET has_custom_allowance = true
        WHERE id in
        (
            SELECT
                ab.id
            FROM annual_billing ab
            JOIN services s on ab.service_id = s.id
            JOIN default_annual_allowance daa on s.organisation_type = daa.organisation_type
            WHERE
                ab.financial_year_start = 2024
                AND daa.valid_from_financial_year_start = 2024
                AND daa.notification_type = 'sms' and ab.free_sms_fragment_limit != 0
                AND ab.free_sms_fragment_limit != daa.allowance
            ORDER BY s.organisation_type, ab.free_sms_fragment_limit
        )
        """
    )

    # update billing for services with a zero allowance last year - either high_volume = true or has_custom = True
    op.execute(
        """
        -- return service id and fy23-24 units used for all services that have zero SMS allowance in fy24
       WITH prev_fy_stats AS (
            SELECT
                ab.id AS annual_billing_24_id,
                coalesce(sum(billable_units * rate_multiplier), 0) AS units_used_in_23
            FROM annual_billing ab
            LEFT OUTER JOIN ft_billing ON
                ab.service_id = ft_billing.service_id
                AND notification_type = 'sms'
                AND bst_date >= '2023-04-01'
                AND bst_date < '2024-04-01'
            WHERE
                ab.financial_year_start = 2024
                AND ab.free_sms_fragment_limit = 0
            GROUP BY
                ab.id
        )
        UPDATE annual_billing
        SET
            high_volume_service_last_year = prev_fy_stats.units_used_in_23 >= 400000,
            has_custom_allowance = prev_fy_stats.units_used_in_23 < 400000
        FROM prev_fy_stats
        WHERE
            prev_fy_stats.annual_billing_24_id = annual_billing.id
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE annual_billing
        SET
            high_volume_service_last_year = false,
            has_custom_allowance = false
        """
    )
