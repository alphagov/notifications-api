"""

Revision ID: 0437_min_numeric_scl_aux_tbls
Revises: 0436_sh_swap_check_for_not_null

"""

revision = "0437_min_numeric_scl_aux_tbls"
down_revision = "0436_sh_swap_check_for_not_null"

from alembic import op
from sqlalchemy import (
    Numeric,
    case,
    cast,
    column,
    func,
    table,
    update,
)


def _get_cases(var, max_scale=7):
    # values used in types must be constants so we need
    # to do this slightly ridiculous case statement covering
    # each scale we expect to encounter
    return case(
        {i: cast(var, Numeric(1000, i)) for i in range(max_scale)},
        value=func.min_scale(var),
        else_=var,
    )


def upgrade():
    conn = op.get_bind()
    conn.execute(update(table("letter_rates", column("rate"))).values(rate=_get_cases(column("rate"))))
    conn.execute(update(table("rates", column("rate"))).values(rate=_get_cases(column("rate"))))


def downgrade():
    pass
