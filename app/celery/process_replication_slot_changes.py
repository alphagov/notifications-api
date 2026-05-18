from app import current_app, notify_celery
from app.cronitor import cronitor
from app.replication.replication_changes_utils import get_replication_changes


# @TODO: this is a temporary task to check the replication slot changes,
# we will need to implement the logic to process the changes and update the dashboard accordingly
@notify_celery.task(bind=True, name="check-replication-slot-changes")
@cronitor("check-replication-slot-changes")
def check_replication_slot_changes(self):
    try:
        changes = get_replication_changes()
        current_app.logger.info(
            "Replication slot changes retrieved",
            extra={
                "celery_task": "check-replication-slot-changes",
                "changes_count": len(changes) if changes else 0,
            },
        )
    except Exception as exc:
        retry_count = self.request.retries
        if retry_count < 3:
            raise self.retry(exc=exc, countdown=2**retry_count) from exc
        else:
            current_app.logger.error(
                "Replication slot query failed after 3 retries",
                exc_info=True,
                extra={"celery_task": "check-replication-slot-changes"},
            )
            raise
