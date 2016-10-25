from app.dao import services_dao
from app.errors import InvalidRequest
from app.models import KEY_TYPE_TEST


def check_service_message_limit(key_type, service):
    if all((key_type != KEY_TYPE_TEST,
            service.restricted)):
        service_stats = services_dao.fetch_todays_total_message_count(service.id)
        if service_stats >= service.message_limit:
            error = 'Exceeded send limits ({}) for today'.format(service.message_limit)

            raise InvalidRequest(error, status_code=429)


def check_template_is_for_notification_type(notification_type, template_type):
    if notification_type != template_type:
        raise InvalidRequest("{0} template is not suitable for {1} notification".format(template_type,
                                                                                        notification_type),
                             status_code=400)


def check_template_is_active(template):
    if template.archived:
        raise InvalidRequest('Template has been deleted', status_code=400)
