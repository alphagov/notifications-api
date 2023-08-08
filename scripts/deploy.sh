#!/usr/bin/env bash

set -eu

# if there's not git dir we're in concourse, because the artifact doesn't include the .git dir
if [[ ! -d ".git" ]]; then

  if [[ $(ls -l ./api-droplet-guid-*.txt | wc -l) != 1 ]]; then
    echo "Error:"
    echo "Exactly one api-droplet-guid file is expected"
    exit 1
  fi
  ORIGINAL_DROPLET_GUID=$(cat ./api-droplet-guid-*.txt)

else

  GIT_REF=$(git rev-parse --short HEAD)
  if [[ ! $(ls ./api-droplet-guid-*-${GIT_REF}.txt) ]]; then
    echo "Error:"
    echo "Missing api-droplet-guid file for this commit (${GIT_REF})"
    echo "Run ./scripts/create-droplet.sh and try again"
    exit 1
  fi
  ORIGINAL_DROPLET_GUID=$(cat ./api-droplet-guid-*-${GIT_REF}.txt)
fi

echo "Original droplet guid: ${ORIGINAL_DROPLET_GUID}"
APP_GUID=$(cf app ${CF_APP} --guid)

#
# Copy droplet
#
echo "Copying droplet..."
DROPLET_GUID=$(cf curl "/v3/droplets?source_guid=${ORIGINAL_DROPLET_GUID}" \
  -X POST \
  -H "Content-type: application/json" \
  -d @<(cat <<END
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
) | jq -r ".guid")

echo "Copied droplet guid: ${DROPLET_GUID}"

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

echo "Set the new droplet for the app"
cf set-droplet ${CF_APP} ${DROPLET_GUID}

DESIRED_INSTANCES=$(cf app ${CF_APP} | grep instances: | cut -d'/' -f2)

if [[ "$DESIRED_INSTANCES" != "0" ]]; then
  echo "Restart the app to pickup the new droplet"
  CF_STARTUP_TIMEOUT=15 cf restart ${CF_APP} --strategy rolling
else
  echo "0 instances required so app is not restarted to avoid scaling up"
fi
