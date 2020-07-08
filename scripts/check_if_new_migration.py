import os
from os.path import dirname, abspath
import requests
import sys


def get_latest_db_migration_to_apply():
    project_dir = dirname(dirname(abspath(__file__)))  # Get the main project directory
    migrations_dir = '{}/migrations/versions/'.format(project_dir)
    migration_files = [migration_file for migration_file in os.listdir(migrations_dir) if migration_file.endswith('py')]
    # sometimes there's a trailing underscore, if script was created with `flask db migrate --rev-id=...`
    latest_file = sorted(migration_files, reverse=True)[0].replace('_.py', '').replace('.py', '')
    return latest_file


def get_current_db_version():
    api_status_url = '{}/_status'.format(os.getenv('API_HOST_NAME'))

    try:
        response = requests.get(api_status_url)
        response.raise_for_status()
        current_db_version = response.json()['db_version']
        return current_db_version
    except requests.exceptions.ConnectionError:
        print(f'Could not make web request to {api_status_url}', file=sys.stderr)
        return ''
    except Exception:  # we expect these to be either either a http status code error, or a json decoding error
        print(
            f'Could not read status endpoint!\n\ncode {response.status_code}\nresponse "{response.text}"',
            file=sys.stderr
        )
        # if we can't make a request to the API, the API is probably down. By returning a blank string (which won't
        # match the filename of the latest migration), we force the migration to run, as the code change to fix the api
        # might involve a migration file.
        return ''


def run():
    if get_current_db_version() == get_latest_db_migration_to_apply():
        print('no')
    else:
        print('yes')


if __name__ == "__main__":
    run()
