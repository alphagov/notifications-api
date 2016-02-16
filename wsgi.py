import os

from app import create_app
from credstash import getAllSecrets

# on aws get secrets and export to env
secrets = getAllSecrets(region="eu-west-1")
for key, val in secrets.items():
    os.environ[key] = val

application = create_app()

if __name__ == "__main__":
        application.run()
