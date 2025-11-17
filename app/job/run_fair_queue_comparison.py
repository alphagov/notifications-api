import os
import sys

# ensure /notifications-api is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ["NOTIFY_ENVIRONMENT"] = "development"

from app import create_app
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("delivery")
create_app(application)
application.app_context().push()

import time

from app.celery.test_fair_queue import debug_fair_queue
from app.config import QueueNames

service_ids = ["tenant-A", "tenant-B", "tenant-C"]
print("Submitting jobs...")

# --- Without fairness ---
for sid in service_ids * 3:
    debug_fair_queue.apply_async(args=[sid], queue=QueueNames.JOBS)
print("✅ Submitted standard SQS jobs (no MessageGroupId).\n")

time.sleep(10)  # give the worker time to drain queue

# --- With fairness ---
for sid in service_ids * 3:
    debug_fair_queue.apply_async(
        args=[sid],
        queue=QueueNames.JOBS,
        headers={"MessageGroupId": str(sid)},
    )
print("✅ Submitted fair SQS jobs (with MessageGroupId).\n")
