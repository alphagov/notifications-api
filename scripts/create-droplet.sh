#!/usr/bin/env bash

set -eux

CF_SPACE=${CF_SPACE:-monitoring}


if [[ -f .git/short_ref ]]; then
  GIT_REF=$(cat .git/short_ref)
else
  GIT_REF=$(git rev-parse --short HEAD)
fi
DROPLET_BUILD_APP="droplet-build-api-${GIT_REF}"

echo "Creating ${DROPLET_BUILD_APP} in ${CF_SPACE}"
cf target -s ${CF_SPACE}
cf create-app ${DROPLET_BUILD_APP}

echo "Applying droplet build app manifest..."
cf apply-manifest -f manifest-droplet.yml --var app_name=${DROPLET_BUILD_APP}

echo "Creating package..."
cf create-package ${DROPLET_BUILD_APP} -p .
PACKAGE_GUID=$(cf curl /v3/apps/$(cf app ${DROPLET_BUILD_APP} --guid)/packages | jq -r '[.resources[] | {created_at, guid}] | sort_by(.created_at) | reverse | .[0].guid')

echo "Staging package to create droplet..."
cf stage-package ${DROPLET_BUILD_APP} --package-guid ${PACKAGE_GUID}
DROPLET_GUID=$(cf curl /v3/apps/$(cf app ${DROPLET_BUILD_APP} --guid)/droplets | jq -r '[.resources[] | {created_at, guid}] | sort_by(.created_at) | reverse | .[0].guid')
echo "Created droplet ${DROPLET_GUID}"

CURRENT_TIME=$(date '+%Y-%m-%dT%H-%M-%SZ')
echo $DROPLET_GUID > api-droplet-guid-${CURRENT_TIME}-${GIT_REF}.txt
