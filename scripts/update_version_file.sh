#!/bin/bash
#
# Update the version file of the project from the Travis build details
#
sed -i -e "s/__build__ =.*/__build__ = \"$TRAVIS_COMMIT\"/g" ./app/version.py
sed -i -e "s/__time__ =.*/__time__ = \"$('date +%Y-%m-%d:%H:%M:%S')\"/g" ./app/version.py