"""
Create Date: 2025-07-07 15:46:53.673184
"""

from alembic import op
from sqlalchemy import text

revision = '0509_delete_broadcast_data'
down_revision = '0508_n_history_templates_index'


def upgrade():
    """
    Removes all existence of broadcast specific services and all their associated data:

    deletes ALL data from the following tables:

    * broadcast_event
    * broadcast_message
    * broadcast_provider_message
    * broadcast_provider_message_number
    * service_broadcast_provider_restriction
    * service_broadcast_settings

    deletes all data linked to a broadcast service from any table with a `service_id` (or a `template_id` for templates
    belonging to a broadcast service).

    this does not touch the following static type tables

    * broadcast_channel_types
    * broadcast_provider_message_status_type
    * broadcast_provider_types
    * broadcast_status_type

    this does not touch the following sequence

    * broadcast_provider_message_number_seq
    """

    conn = op.get_bind()
    results = conn.execute(text("SELECT service_id FROM service_broadcast_settings;"))
    res = results.fetchall()
    broadcast_service_ids = tuple(x.service_id for x in res)

    # these are broadly alphabetical, but with some lines reordered due to precedence (eg needing to delete
    # user_folder_permissions before we can delete the template folders they reference)
    delete_statements = [
        # step 1: delete the entire tables for the broadcast specific things
        "DELETE FROM broadcast_provider_message_number;",
        "DELETE FROM broadcast_provider_message;",
        "DELETE FROM broadcast_event;",
        "DELETE FROM broadcast_message;",
        "DELETE FROM service_broadcast_settings;",
        "DELETE FROM service_broadcast_provider_restriction;",
        # all these tables have service_id, so need to be deleted before we can delete the service,
        # (note this includes templates as well, which we need to delete),
    ]

    if broadcast_service_ids:
        delete_statements += [
            "DELETE FROM notifications WHERE service_id in :service_ids;",
            "DELETE FROM notification_history WHERE service_id in :service_ids;",
            "DELETE FROM annual_billing WHERE service_id in :service_ids;",
            "DELETE FROM api_keys WHERE service_id in :service_ids;",
            "DELETE FROM api_keys_history WHERE service_id in :service_ids;",
            "DELETE FROM complaints WHERE service_id in :service_ids;",
            "DELETE FROM service_sms_senders WHERE service_id in :service_ids;",
            "DELETE FROM ft_billing WHERE service_id in :service_ids;",
            "DELETE FROM ft_notification_status WHERE service_id in :service_ids;",
            "DELETE FROM inbound_numbers WHERE service_id in :service_ids;",
            "DELETE FROM inbound_sms WHERE service_id in :service_ids;",
            "DELETE FROM inbound_sms_history WHERE service_id in :service_ids;",
            "DELETE FROM invited_users WHERE service_id in :service_ids;",
            "DELETE FROM jobs WHERE service_id in :service_ids;",
            "DELETE FROM permissions WHERE service_id in :service_ids;",
            "DELETE FROM returned_letters WHERE service_id in :service_ids;",
            "DELETE FROM service_callback_api WHERE service_id in :service_ids;",
            "DELETE FROM service_callback_api_history WHERE service_id in :service_ids;",
            "DELETE FROM service_contact_list WHERE service_id in :service_ids;",
            "DELETE FROM service_data_retention WHERE service_id in :service_ids;",
            "DELETE FROM service_email_branding WHERE service_id in :service_ids;",
            "DELETE FROM service_email_reply_to WHERE service_id in :service_ids;",
            "DELETE FROM service_join_requests WHERE service_id in :service_ids;",
            "DELETE FROM service_letter_branding WHERE service_id in :service_ids;",
            "DELETE FROM service_permissions WHERE service_id in :service_ids;",
            "DELETE FROM service_whitelist WHERE service_id in :service_ids;",
            "DELETE FROM user_folder_permissions WHERE service_id in :service_ids",
            "DELETE FROM template_folder_map WHERE template_id in (SELECT id FROM templates WHERE service_id in :service_ids);",
            "DELETE FROM template_redacted WHERE template_id in (SELECT id FROM templates WHERE service_id in :service_ids);",
            "DELETE FROM template_folder WHERE service_id in :service_ids;",
            "DELETE FROM templates WHERE service_id in :service_ids;",
            "DELETE FROM templates_history WHERE service_id in :service_ids;",
            "DELETE FROM service_letter_contacts WHERE service_id in :service_ids;",
            "DELETE FROM unsubscribe_request WHERE service_id in :service_ids;",
            "DELETE FROM unsubscribe_request_history WHERE service_id in :service_ids;",
            "DELETE FROM unsubscribe_request_report WHERE service_id in :service_ids;",
            "DELETE FROM user_to_service WHERE service_id in :service_ids;",
            # now we can finally delete the services
            "DELETE FROM services WHERE id in :service_ids;",
            "DELETE FROM services_history WHERE id in :service_ids;",
        ]

    for delete_statement in delete_statements:
        conn.execute(text(delete_statement), {"service_ids": broadcast_service_ids})


def downgrade():
    # undowngradeable!
    pass
