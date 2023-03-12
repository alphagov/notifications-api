from flask import Blueprint, current_app

test_blueprint = Blueprint("test", "test")
admin_test_blueprint = Blueprint("admin_test", "admin_test")


@test_blueprint.route("/log")
def log_view():
    """A view that emits a log statement"""
    current_app.logger.info("a log message")
    return "OK"


@admin_test_blueprint.route("/admin-log")
def admin_log_view():
    """A view that emits a log statement"""
    current_app.logger.info("a log message")
    return "OK"
