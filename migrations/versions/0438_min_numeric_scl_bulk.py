"""

Revision ID: 0438_min_numeric_scl_bulk
Revises: 0437_min_numeric_scl_aux_tbls

"""

revision = "0438_min_numeric_scl_bulk"
down_revision = "0437_min_numeric_scl_aux_tbls"

import datetime
from itertools import accumulate, repeat
import uuid

from alembic import op
from sqlalchemy import (
    DateTime,
    Numeric,
    and_,
    case,
    cast,
    column,
    func,
    select,
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
        n_blocks = 64
        block_step = (1 << 128) // n_blocks

        notifications = table(
            "notifications",
            column("id", UUID(as_uuid=True)),
            column("rate_multiplier"),
        )

        for block_start in range(0, 1 << 128, block_step):
            block_end = block_start + block_step
            conn.execute(
                update(notifications)
                .values(rate_multiplier=_get_cases(notifications.c.rate_multiplier))
                .where(
                    and_(
                        notifications.c.id >= uuid.UUID(int=block_start),
                        # closed interval because (1<<128) itself isn't representable as a UUID
                        notifications.c.id <= uuid.UUID(int=block_end - 1),
                    )
                )
            )

        ft_billing = table(
            "ft_billing",
            column("template_id", UUID(as_uuid=True)),
            column("rate"),
        )

        for block_start in range(0, 1 << 128, block_step):
            block_end = block_start + block_step
            conn.execute(
                update(ft_billing)
                .values(rate=_get_cases(ft_billing.c.rate))
                .where(
                    and_(
                        ft_billing.c.template_id >= uuid.UUID(int=block_start),
                        # closed interval because (1<<128) itself isn't representable as a UUID
                        ft_billing.c.template_id <= uuid.UUID(int=block_end - 1),
                    )
                )
            )

        block_period = datetime.timedelta(hours=1)

        nhistory = table(
            "notification_history",
            column("created_at", DateTime),
            column("rate_multiplier"),
        )

        min_max_row = conn.execute(select(func.min(nhistory.c.created_at), func.max(nhistory.c.created_at))).first()

        if min_max_row:
            created_at_min, created_at_max = min_max_row

            for block_start in accumulate(
                repeat(block_period),
                initial=created_at_min,
            ):
                block_end = block_start + block_period
                conn.execute(
                    update(nhistory)
                    .values(rate_multiplier=_get_cases(nhistory.c.rate_multiplier))
                    .where(
                        and_(
                            nhistory.c.created_at >= block_start,
                            nhistory.c.created_at < block_end,
                        )
                    )
                )
                if block_end > created_at_max:
                    break


def downgrade():
    pass
