"""

Revision ID: 0379_update_archived_users
Revises: 0378_remove_doc_download_perm
Create Date: 2022-10-10 12:45:47.519550

"""

import textwrap

from alembic import op
from flask import current_app
from sqlalchemy import text

revision = "0379_update_archived_users"
down_revision = "0378_remove_doc_download_perm"


def get_archived_db_column_value(column, date):
    return f"_archived_{date}_{column}"


def upgrade():
    conn = op.get_bind()

    # Get all users with an archived email address (but not a "new style" redacted email address - this should be 0
    # anyway).
    # For each user:
    #   Get their user id
    #   If they have an archive_user event in the events table, get the event_id
    #   Get their current user email address (_archived_ format)
    #   Get the date they were archived by extracting it from their archived email address
    #   Get their original email address by extracting it from the un-redacted archived email address.
    results = conn.execute(
        text(
            textwrap.dedent(
                """
                SELECT
                    users.id as user_id,
                    events.id AS event_id,
                    substring(users.email_address, '_archived_(\d{4}[-_]\d{1,2}[-_]\d{1,2})_.*')
                    AS archival_date,
                    substring(users.email_address, '_archived_\d{4}[-_]\d{1,2}[-_]\d{1,2}_(.*)')
                    AS original_email_address
                FROM users
                LEFT JOIN events on users.id = (events.data->>'user_id')::uuid AND events.event_type = 'archive_user'
                WHERE
                    users.state = 'inactive'
                    AND NOT users.email_address LIKE CONCAT('_archived_%@', :notify_email_domain)
                ORDER BY
                    users.id;
                """  # noqa: W605
            )
        ),
        notify_email_domain=current_app.config["NOTIFY_EMAIL_DOMAIN"],
    )

    rows = results.fetchall()

    email_domain = current_app.config["NOTIFY_EMAIL_DOMAIN"]
    users_to_update = [
        {
            "user_id": user_id,
            "desired_email_address": get_archived_db_column_value(f"{user_id}@{email_domain}", date=archival_date),
        }
        for user_id, _, archival_date, _ in rows
    ]
    print(f"Updating {len(users_to_update)} users.")
    if users_to_update:
        conn.execute(
            text(
                textwrap.dedent(
                    """
                    UPDATE users
                    SET
                        name = 'Archived user',
                        email_address = :desired_email_address,
                        updated_at = now()
                    WHERE
                        id = :user_id
                    """
                )
            ),
            users_to_update,
        )

    events_to_update = [
        {
            "event_id": event_id,
            "original_email_address": original_email_address,
        }
        for _, event_id, _, original_email_address in rows
        if event_id is not None
    ]
    print(f"Updating {len(events_to_update)} events.")
    if events_to_update:
        conn.execute(
            text(
                textwrap.dedent(
                    """
                    UPDATE events
                    SET
                        data = events.data::jsonb || jsonb_build_object('user_email_address', :original_email_address)
                    WHERE
                        id = :event_id
                        AND events.data->>'user_email_address' IS NULL
                    """
                )
            ),
            events_to_update,
        )


def downgrade():
    pass
