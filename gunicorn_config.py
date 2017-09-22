def worker_abort(worker):
    worker.log.info("worker received ABORT")
    import sys, traceback
    for threadId, stack in sys._current_frames().items():
        worker.log.info(''.join(traceback.format_stack(stack)))
