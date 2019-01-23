import os
import sys

def write_stdout(s):
    sys.stdout.write(s)
    sys.stdout.flush()

def write_stderr(s):
    sys.stderr.write(s)
    sys.stderr.flush()

def kill_supervisor():
    os.system('pkill -15 -f supervisord')

def main():
    while True:
        write_stdout('READY\n')

        line = sys.stdin.readline()
        if 'PROCESS_STATE_FATAL' in line or 'PROCESS_STATE_UNKNOWN' in line:
            kill_supervisor()

        write_stdout('RESULT 2\nOK')

if __name__ == '__main__':
    main()
