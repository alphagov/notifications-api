import yaml

from app.config import QueueNames


def test_queue_names_set_in_manifest_delivery_base_correctly():
    with open("manifest-delivery-base.yml", 'r') as stream:
        search = ' -Q '
        yml_commands = [y['command'] for y in yaml.load(stream)['applications']]

        watched_queues = set()
        for command in yml_commands:
            start_of_queue_arg = command.find(search)
            if start_of_queue_arg > 0:
                start_of_queue_names = start_of_queue_arg + len(search)
                queues = command[start_of_queue_names:].split(',')
                for q in queues:
                    if "2>" in q:
                        q = q.split("2>")[0].strip()
                    watched_queues.add(q)

        # ses-callbacks isn't used in api (only used in SNS lambda)
        ignored_queues = {'ses-callbacks'}
        watched_queues -= ignored_queues

        assert watched_queues == set(QueueNames.all_queues())
