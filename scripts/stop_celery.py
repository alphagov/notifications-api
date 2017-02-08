#!/usr/bin/env python3
"""

Scipt used to stop celery in AWS environments.
This is used from upstart to issue a TERM signal to the master celery process.

This will then allow the worker threads to stop, after completing
whatever tasks that are in flight.

Note the script blocks for up to 15minutes, which is long enough to allow our
longest possible task to complete. If it can return quicker it will.

Usage:
    ./stop_celery.py <celery_pid_file>

Example:
    ./stop_celery.py /tmp/celery.pid
"""

import os
from docopt import docopt
import re
import subprocess
from time import sleep


def strip_white_space(from_this):
    return re.sub(r'\s+', '', from_this)


def get_pid_from_file(filename):
    """
    Open the file which MUST contain only the PID of the master celery process.
    This is written to disk by the start celery command issued by upstart
    """
    with open(filename) as f:
        celery_pid = f.read()
    return strip_white_space(celery_pid)


def issue_term_signal_to_pid(pid):
    """
    Issues a TERM signal (15) to the master celery process.

    This method attempts to print out any response from this subprocess call. However this call is generally silent.
    """
    result = subprocess.Popen(['kill', '-15', pid], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in result.stdout.readlines():
        print(line.rstrip())
    for line in result.stderr.readlines():
        print(line.rstrip())


def pid_still_running(pid):
    """
    uses the proc filesystem to identify if the celery master pid is still around.

    Once the process stops this file no longer exists. Slim possibilty of a race condition here.
    """
    if os.path.exists("/proc/" + pid):
        return True
    return False


if __name__ == "__main__":
    arguments = docopt(__doc__)
    celery_pid_file = arguments['<celery_pid_file>']

    celery_pid = get_pid_from_file(celery_pid_file)

    issue_term_signal_to_pid(celery_pid)

    """
    Blocking loop to check for the still running process.
    5 seconds between loops
    180 loops
    Maximum block time of 900 seconds (15 minutes)
    """
    iteration = 0
    while pid_still_running(celery_pid) and iteration < 180:
        print("waited for ", iteration * 5, " secs")
        sleep(5)
        iteration += 1
