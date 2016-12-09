import os

from app import create_app
from credstash import getAllSecrets


# On AWS get secrets and export to env, skip this on Cloud Foundry
if os.getenv('VCAP_SERVICES') is None:
    os.environ.update(getAllSecrets(region="eu-west-1"))

application = create_app()

if __name__ == "__main__":
    application.run()
