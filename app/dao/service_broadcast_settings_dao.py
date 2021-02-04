from app import db
from app.models import ServiceBroadcastSettings
from app.dao.dao_utils import transactional


@transactional
def insert_or_update_service_broadcast_settings(service, channel, provider_restriction=None):
    if not service.service_broadcast_settings:
        settings = ServiceBroadcastSettings()
        settings.service = service
        settings.channel = channel
        db.session.add(settings)
    else:
        service.service_broadcast_settings.channel = channel
        db.session.add(service.service_broadcast_settings)
