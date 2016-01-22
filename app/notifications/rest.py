from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app import notify_alpha_client
from app import api_user
from app.dao import (templates_dao, services_dao)
import re

mobile_regex = re.compile("^\\+44[\\d]{10}$")

notifications = Blueprint('notifications', __name__)


@notifications.route('/<notification_id>', methods=['GET'])
def get_notifications(notification_id):
    return jsonify(notify_alpha_client.fetch_notification_by_id(notification_id)), 200


@notifications.route('/sms', methods=['POST'])
def create_sms_notification():
    notification = request.get_json()['notification']
    errors = {}
    to, to_errors = validate_to(notification, api_user['client'])
    print("create sms")
    print(notification)
    template, template_errors = validate_template(notification, api_user['client'])
    if to_errors['to']:
        errors.update(to_errors)
    if template_errors['template']:
        errors.update(template_errors)
    if errors:
        return jsonify(result="error", message=errors), 400
    return jsonify(notify_alpha_client.send_sms(
        mobile_number=to,
        message=template)), 200


@notifications.route('/email', methods=['POST'])
def create_email_notification():
    notification = request.get_json()['notification']
    errors = {}
    for k in ['to', 'from', 'subject', 'message']:
        k_error = validate_required_and_something(notification, k)
        if k_error:
            errors.update(k_error)

    if errors:
        return jsonify(result="error", message=errors), 400

    return jsonify(notify_alpha_client.send_email(
        notification['to'],
        notification['message'],
        notification['from'],
        notification['subject']))


def validate_to(json_body, service_id):
    errors = {"to": []}
    mob = json_body.get('to', None)
    if not mob:
        errors['to'].append('Required data missing')
    else:
        if not mobile_regex.match(mob):
            errors['to'].append('invalid phone number, must be of format +441234123123')
        if service_id != current_app.config.get('ADMIN_CLIENT_USER_NAME'):
            service = services_dao.get_model_services(service_id=service_id)
            if service.restricted:
                valid = False
                for usr in service.users:
                    if mob == usr.mobile_number:
                        valid = True
                        break
                if not valid:
                    errors['to'].append('Invalid phone number for restricted service')
    return mob, errors


def validate_template(json_body, service_id):
    errors = {"template": []}
    template_id = json_body.get('template', None)
    content = ''
    if not template_id:
        errors['template'].append('Required data missing')
    else:
        if service_id == current_app.config.get('ADMIN_CLIENT_USER_NAME'):
            content = json_body['template']
        else:
            try:
                template = templates_dao.get_model_templates(
                    template_id=json_body['template'],
                    service_id=service_id)
                content = template.content
            except:
                errors['template'].append("Unable to load template.")
    return content, errors


def validate_required_and_something(json_body, field):
    errors = []
    if field not in json_body and json_body[field]:
        errors.append('Required data for field.')
    return {field: errors} if errors else None
