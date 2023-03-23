from flask import Blueprint, current_app

test_no_auth_blueprint = Blueprint("test", "test")
test_admin_auth_blueprint = Blueprint("admin_test", "admin_test")


@test_no_auth_blueprint.route("/log")
def log_view():
    """A view that emits a log statement"""
    current_app.logger.info("a log message")
    return "OK"


@test_admin_auth_blueprint.route("/admin-log")
def admin_log_view():
    """A view that emits a log statement"""
    current_app.logger.info("a log message")
    return "OK"
