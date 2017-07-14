
class QueueNames(object):
    PERIODIC = 'periodic-tasks'
    PRIORITY = 'priority-tasks'
    DATABASE = 'database-tasks'
    SEND = 'send-tasks'
    RESEARCH_MODE = 'research-mode-tasks'
    STATISTICS = 'statistics-tasks'
    JOBS = 'job-tasks'
    RETRY = 'retry-tasks'
    NOTIFY = 'notify-internal-tasks'
    PROCESS_FTP = 'process-ftp-tasks'

    @staticmethod
    def all_queues():
        return [
            QueueNames.PRIORITY,
            QueueNames.PERIODIC,
            QueueNames.DATABASE,
            QueueNames.SEND,
            QueueNames.RESEARCH_MODE,
            QueueNames.STATISTICS,
            QueueNames.JOBS,
            QueueNames.RETRY,
            QueueNames.NOTIFY,
            QueueNames.PROCESS_FTP
        ]
