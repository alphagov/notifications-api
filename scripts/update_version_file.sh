#!/bin/bash
#
# Update the version file of the project from the Travis build details
#
sed -i -e "s/__travis_commit__ =.*/__travis_commit__ = \"$TRAVIS_COMMIT\"/g" ./app/version.py
sed -i -e "s/__travis_job_number__ =.*/__travis_job_number__ = \"$TRAVIS_BUILD_NUMBER\"/g" ./app/version.py
sed -i -e "s/__time__ =.*/__time__ = \"$(date +%Y-%m-%d:%H:%M:%S)\"/g" ./app/version.py