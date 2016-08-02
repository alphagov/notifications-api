import os

from app import create_app
from credstash import getAllSecrets


# on aws get secrets and export to env
os.environ.update(getAllSecrets(region="eu-west-1"))

application = create_app()

if __name__ == "__main__":
    application.run()
