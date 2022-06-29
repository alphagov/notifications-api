#!/usr/bin/env bash

set -eux

CF_SPACE=${CF_SPACE:-monitoring}

[[ ! -f ./.git/short_ref ]] && $(git rev-parse --short HEAD) > ./.git/short_ref
GIT_REF=$(cat .git/short_ref)
DROPLET_BUILD_APP="droplet-build-api-${GIT_REF}"

echo "Creating ${DROPLET_BUILD_APP} in ${CF_SPACE}"
cf target -s ${CF_SPACE}
cf create-app ${DROPLET_BUILD_APP}

echo "Creating package..."
cf create-package ${DROPLET_BUILD_APP} -p .
PACKAGE_GUID=$(cf packages ${DROPLET_BUILD_APP} | tail -n 1 | cut -d" " -f 1)

echo "Staging package to create droplet..."
cf stage-package ${DROPLET_BUILD_APP} --package-guid ${PACKAGE_GUID}
DROPLET_GUID=$(cf droplets ${DROPLET_BUILD_APP} | tail -n 1 | cut -d" " -f 1)
echo "Created droplet ${DROPLET_GUID}"

CURRENT_TIME=$(date '+%Y-%m-%dT%H-%M-%SZ')
echo $DROPLET_GUID > api-droplet-guid-${CURRENT_TIME}-${GIT_REF}.txt
