from time import sleep

from app import notify_celery


@notify_celery.task(name="debug-fair-queue")
def debug_fair_queue(service_id):
    import random

    delay = random.uniform(0.1, 0.5)
    print(f"[FairQueueTest] 🏁 Starting job for {service_id} (delay={delay:.2f}s)")
    sleep(delay)
    print(f"[FairQueueTest] ✅ Finished job for {service_id}")
