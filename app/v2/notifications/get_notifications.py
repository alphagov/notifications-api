from app.v2.notifications import notification_blueprint


@notification_blueprint.route("/<uuid:id>", methods=['GET'])
def get_notification_by_id(id):
    pass


@notification_blueprint.route("/", methods=['GET'])
def get_notifications():
    # validate notifications request arguments
    # fetch all notifications
    # return notifications_response schema
    pass
