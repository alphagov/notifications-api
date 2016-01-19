from app import create_app
from credstash import getAllSecrets

secrets = getAllSecrets(region="eu-west-1")

application = create_app('live', secrets)

if __name__ == "__main__":
        application.run()
