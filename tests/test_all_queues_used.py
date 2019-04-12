from app.config import QueueNames


def test_queue_names_set_in_paas_app_wrapper():
    with open("scripts/paas_app_wrapper.sh", 'r') as stream:
        search = ' -Q '

        watched_queues = set()
        for line in stream.readlines():
            start_of_queue_arg = line.find(search)
            if start_of_queue_arg > 0:
                start_of_queue_names = start_of_queue_arg + len(search)
                end_of_queue_names = line.find('2>') if '2>' in line else len(line)
                watched_queues.update({q.strip() for q in line[start_of_queue_names:end_of_queue_names].split(',')})

        # ses-callbacks isn't used in api (only used in SNS lambda)
        ignored_queues = {'ses-callbacks'}
        assert watched_queues == set(QueueNames.all_queues()) | ignored_queues
