### What is it?

This is a simple static error page to present to API users in case of a (planned) downtime.
It is deployed as an individual app and remains dormant until a route is assigned to it.
It returns a 503 error code and a standard json response for all routes.


### How do I use it?

It should already be deployed, but if not (or if you need to make changes to the nginx config) you can deploy it by running

    cf push notify-api-failwhale

To enable it you need to run

    make <environment> enable-failwhale

and to disable it

    make <environment> disable-failwhale


Where `<environment>` is any of

- preview
- staging
- production
