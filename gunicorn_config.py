import sys
import traceback


def worker_abort(worker):
    worker.log.info("worker received ABORT")
    for threadId, stack in sys._current_frames().items():
        worker.log.info(''.join(traceback.format_stack(stack)))
