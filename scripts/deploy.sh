#!/usr/bin/env bash

set -eu

echo $(pwd)

GIT_REF=$(cat ./.git/short_ref)
ORIGINAL_DROPLET_GUID=$(cat ./api-droplet-guid-*-${GIT_REF}.txt)
APP_GUID=$(cf app ${CF_APP} --guid)


#
# Copy droplet
#
echo "Copying droplet..."
cat <<END > copy-droplet-${CF_APP}.json
{
    "relationships": {
      "app": {
        "data": {
          "guid": "${APP_GUID}"
        }
      }
    }
}
END

DROPLET_GUID=$(cf curl "/v3/droplets?source_guid=${ORIGINAL_DROPLET_GUID}" \
  -X POST \
  -H "Content-type: application/json" \
  -d @./copy-droplet-${CF_APP}.json | jq -r ".guid")

echo "Droplet GUID: ${DROPLET_GUID}"

# wait a bit for the droplet to be copied
sleep 5

#
# Apply manifest before the deployment
# docs:
#   https://v3-apidocs.cloudfoundry.org/version/3.116.0/index.html#apply-a-manifest-to-a-space
#   https://cli.cloudfoundry.org/en-US/v7/apply-manifest.html
#

echo "Applying manifest..."
cf apply-manifest -f ${CF_MANIFEST_PATH}

#
# Trigger a new deployment using the new droplet guid
#
cat <<END > deployment-${CF_APP}.json
{
  "droplet": {
    "guid": "${DROPLET_GUID}"
  },
  "strategy": "rolling",
  "relationships": {
    "app": {
      "data": {
        "guid": "${APP_GUID}"
      }
    }
  }
}
END

echo "Triggering a new deployment..."
DEPLOYMENT_GUID=$(cf curl "/v3/deployments" \
  -X POST \
  -H "Content-type: application/json" \
  -d @./deployment-${CF_APP}.json | jq -r ".guid")

echo "Deployment GUID: ${DEPLOYMENT_GUID}"

#
# Wait for 15 minutes for the deployment to reach "FINALIZED" status
# If it doesn't, then it will exit with an exit status of 124 according to `timeout --help`
#
timeout 15m bash -c -- "until [[ \${STATUS} == FINALIZED ]]; do sleep 5; STATUS=\$(cf curl v3/deployments/${DEPLOYMENT_GUID} | jq -r \".status.value\"); echo \"Deployment status: \${STATUS}\"; done"
