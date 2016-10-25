from app.v2.notifications import notification_blueprint


@notification_blueprint.route('/sms', methods=['POST'])
def post_sms_notification():
    # # get service
    # service = services_dao.dao_fetch_service_by_id(api_user.service_id)
    # # validate input against json schema (not marshmallow)
    # form = validate(request.get_json(), post_sms_request)
    #
    # # following checks will be in a common function for all versions of the endpoint.
    # # check service has not exceeded the sending limit
    # check_service_message_limit(api_user.key_type, service)
    # template = templates_dao.dao_get_template_by_id_and_service_id(
    #     template_id=form['template_id'],
    #     service_id=service.id
    # )
    # # check template is for sms
    # check_template_is_for_notification_type(SMS_TYPE, template.template_type)
    # # check template is not archived
    # check_template_is_active(template)
    # # check service is allowed to send
    # service_can_send_to_recipient(form['phone_number'], api_user.key_type, service)
    # # create body of message (create_template_object_for_notification)
    # create_template_object_for_notification(template, form.get('personalisation', {}))
    # # persist notification
    # # send sms to provider queue for research mode queue
    #

    # validate post form against post_sms_request schema
    # validate service
    # validate template
    # create content
    # persist notification
    # send notification to queue
    # return post_sms_response schema
    return "post_sms_response schema", 201


@notification_blueprint.route('/email', methods=['POST'])
def post_email_notification():
    # validate post form against post_email_request schema
    # validate service
    # validate template
    # persist notification
    # send notification to queue
    # create content
    # return post_email_response schema
    pass
