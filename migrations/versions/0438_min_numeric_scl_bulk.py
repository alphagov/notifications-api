"""

Revision ID: 0438_min_numeric_scl_bulk
Revises: 0437_min_numeric_scl_aux_tbls

"""

revision = "0438_min_numeric_scl_bulk"
down_revision = "0437_min_numeric_scl_aux_tbls"

import uuid

from alembic import op
from sqlalchemy import (
    Numeric,
    and_,
    case,
    cast,
    column,
    func,
    table,
    update,
)
from sqlalchemy.dialects.postgresql import UUID


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
    # the following operations should be idempotent, so in the case of a failure,
    # re-applying all in a retry should cause no issues

    with op.get_context().autocommit_block():
        conn = op.get_bind()

        # apply in blocks to avoid locking whole table at once
        n_blocks = 16
        block_step = (1 << 128) // n_blocks

        for table_name in (
            "notifications",
            "notification_history",
        ):
            _table = table(
                table_name,
                column("id", UUID(as_uuid=True)),
                column("rate_multiplier"),
            )

            for block_start in range(0, 1 << 128, block_step):
                block_end = block_start + block_step
                conn.execute(
                    update(_table)
                    .values(rate_multiplier=_get_cases(_table.c.rate_multiplier))
                    .where(
                        and_(
                            _table.c.id >= uuid.UUID(int=block_start),
                            # closed interval because (1<<128) itself isn't representable as a UUID
                            _table.c.id <= uuid.UUID(int=block_end - 1),
                        )
                    )
                )

        _table = table(
            "ft_billing",
            column("template_id", UUID(as_uuid=True)),
            column("rate"),
        )

        for block_start in range(0, 1 << 128, block_step):
            block_end = block_start + block_step
            conn.execute(
                update(_table)
                .values(rate=_get_cases(_table.c.rate))
                .where(
                    and_(
                        _table.c.template_id >= uuid.UUID(int=block_start),
                        # closed interval because (1<<128) itself isn't representable as a UUID
                        _table.c.template_id <= uuid.UUID(int=block_end - 1),
                    )
                )
            )


def downgrade():
    pass
