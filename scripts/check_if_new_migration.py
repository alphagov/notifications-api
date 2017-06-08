import os
from os.path import dirname, abspath
import requests
import sys


def get_latest_db_migration_to_apply():
    project_dir = dirname(dirname(abspath(__file__)))  # Get the main project directory
    migrations_dir = '{}/migrations/versions/'.format(project_dir)
    migration_files = [migration_file for migration_file in os.listdir(migrations_dir) if migration_file.endswith('py')]
    latest_file = sorted(migration_files, reverse=True)[0].replace('.py', '')
    return latest_file


def get_current_db_version():
    api_status_url = '{}/_status'.format(os.getenv('API_HOST_NAME'))
    response = requests.get(api_status_url)

    if response.status_code != 200:
        sys.exit('Could not make a request to the API: {}'.format())

    current_db_version = response.json()['db_version']
    return current_db_version


def run():
    if get_current_db_version() == get_latest_db_migration_to_apply():
        print('no')
    else:
        print('yes')


if __name__ == "__main__":
    run()
