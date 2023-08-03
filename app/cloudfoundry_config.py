import json
import os


def extract_cloudfoundry_config():
    vcap_services = json.loads(os.environ["VCAP_SERVICES"])

    # Postgres config
    if "SQLALCHEMY_DATABASE_URI" not in os.environ:
        os.environ["SQLALCHEMY_DATABASE_URI"] = vcap_services["postgres"][0]["credentials"]["uri"].replace(
            "postgres", "postgresql"
        )
    # Redis config
    if "REDIS_URL" not in os.environ:
        os.environ["REDIS_URL"] = vcap_services["redis"][0]["credentials"]["uri"]
