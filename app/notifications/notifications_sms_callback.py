from flask import Blueprint
from flask import current_app
from flask import json
from flask import request, jsonify

from app.celery.process_sms_client_response_tasks import process_sms_client_response
from app.config import QueueNames
from app.errors import InvalidRequest, register_errors

sms_callback_blueprint = Blueprint("sms_callback", __name__, url_prefix="/notifications/sms")
register_errors(sms_callback_blueprint)


@sms_callback_blueprint.route('/mmg', methods=['POST'])
def process_mmg_response():
    client_name = 'MMG'
    data = json.loads(request.data)
    errors = validate_callback_data(data=data,
                                    fields=['status', 'CID'],
                                    client_name=client_name)
    if errors:
        raise InvalidRequest(errors, status_code=400)

    status = str(data.get('status'))
    substatus = str(data.get('substatus'))

    provider_reference = data.get('CID')

    process_sms_client_response.apply_async(
        [status, provider_reference, client_name, substatus],
        queue=QueueNames.SMS_CALLBACKS,
    )

    safe_to_log = data.copy()
    safe_to_log.pop("MSISDN")
    current_app.logger.debug(
        f"Full delivery response from {client_name} for notification: {provider_reference}\n{safe_to_log}"
    )

    return jsonify(result='success'), 200


@sms_callback_blueprint.route('/firetext', methods=['POST'])
def process_firetext_response():
    client_name = 'Firetext'
    errors = validate_callback_data(data=request.form,
                                    fields=['status', 'reference'],
                                    client_name=client_name)
    if errors:
        raise InvalidRequest(errors, status_code=400)

    status = request.form.get('status')
    code = request.form.get('code')
    provider_reference = request.form.get('reference')

    safe_to_log = dict(request.form).copy()
    safe_to_log.pop('mobile')
    current_app.logger.debug(
        f"Full delivery response from {client_name} for notification: {provider_reference}\n{safe_to_log}"
    )

    process_sms_client_response.apply_async(
        [status, provider_reference, client_name, code],
        queue=QueueNames.SMS_CALLBACKS,
    )

    return jsonify(result='success'), 200


def validate_callback_data(data, fields, client_name):
    errors = []
    for f in fields:
        if not str(data.get(f, '')):
            error = "{} callback failed: {} missing".format(client_name, f)
            errors.append(error)
    return errors if len(errors) > 0 else None
