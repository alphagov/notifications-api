from datetime import datetime

from flask import current_app

from app import db
from app.dao.dao_utils import transactional, version_class
from app.models import (
    Service,
    ServiceBroadcastSettings,
    ServicePermission,
    Organisation,
    BROADCAST_TYPE,
    EMAIL_AUTH_TYPE
)


@transactional
@version_class(Service)
def set_broadcast_service_type(service, service_mode, broadcast_channel, provider_restriction):
    insert_or_update_service_broadcast_settings(
        service, channel=broadcast_channel, provider_restriction=provider_restriction
    )

    # Remove all permissions and add broadcast permission
    if not service.has_permission(BROADCAST_TYPE):
        service_permission = ServicePermission(service_id=service.id, permission=BROADCAST_TYPE)
        db.session.add(service_permission)

    ServicePermission.query.filter(
        ServicePermission.service_id == service.id,
        ServicePermission.permission != BROADCAST_TYPE,
        # Email auth is an exception to the other service permissions (which relate to what type
        # of notifications a service can send) where a broadcast service is allowed to have the
        # email auth permission (but doesn't have to)
        ServicePermission.permission != EMAIL_AUTH_TYPE
    ).delete()

    # Refresh the service object as it has references to the service permissions but we don't yet
    # want to commit the permission changes incase all of this needs to rollback
    db.session.refresh(service)

    # Set service count as live false always
    service.count_as_live = False

    # Set service into training mode or live mode
    if service_mode == "live":
        if service.restricted:
            # Only update the go live at timestamp if this if moving from training mode
            # to live mode, not if it's moving from one type of live mode service to another
            service.go_live_at = datetime.utcnow()
        service.restricted = False
    else:
        service.restricted = True
        service.go_live_at = None

    # Add service to organisation
    organisation = Organisation.query.filter_by(
        id=current_app.config['BROADCAST_ORGANISATION_ID']
    ).one()
    service.organisation_id = organisation.id
    service.organisation_type = organisation.organisation_type
    service.crown = organisation.crown

    db.session.add(service)


def insert_or_update_service_broadcast_settings(service, channel, provider_restriction=None):
    if not service.service_broadcast_settings:
        settings = ServiceBroadcastSettings()
        settings.service = service
        settings.channel = channel
        settings.provider = provider_restriction
        db.session.add(settings)
    else:
        service.service_broadcast_settings.channel = channel
        service.service_broadcast_settings.provider = provider_restriction
        db.session.add(service.service_broadcast_settings)
