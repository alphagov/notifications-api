# To create a new worker app

You need to:
1. Create new entries for your app in `manifest.yml.j2` and `scripts/paas_app_wrapper.sh` ([example](https://github.com/alphagov/notifications-api/pull/2486/commits/6163ca8b45813ff59b3a879f9cfcb28e55863e16))
1. Update the jenkins deployment job in the notifications-aws repo ([example](https://github.com/alphagov/notifications-aws/commit/69cf9912bd638bce088d4845e4b0a3b11a2cb74c#diff-17e034fe6186f2717b77ba277e0a5828))
1. Add the new worker's log group to the list of logs groups we get alerts about and we ship them to kibana ([example](https://github.com/alphagov/notifications-aws/commit/69cf9912bd638bce088d4845e4b0a3b11a2cb74c#diff-501ffa3502adce988e810875af546b97))
1. Optionally add it to the autoscaler ([example](https://github.com/alphagov/notifications-paas-autoscaler/commit/16d4cd0bdc851da2fab9fad1c9130eb94acf3d15))

**Important:**

Before pushing the deployment change on jenkins, read below about the first time deployment.

## First time deployment of your new worker

Our deployment flow requires that the app is present in order to proceed with the deployment.

This means that the first deployment of your app must happen manually.

To do this:

1. Ensure your code is backwards compatible
1. From the root of this repo run `CF_APP=<APP_NAME> make <cf-space> cf-push`

Once this is done, you can push your deployment changes to jenkins to have your app deployed on every deployment.
