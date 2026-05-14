# otel_metrics

This module was named `otel_metrics` so it wouldn't conflict with the `metrics`
field in `app/__init__.py`.

Once we've migrated away from the GDS metrics lib entirely we can rename this
module to simply `metrics`.

**n.b. when adding new metrics and/or labels here, you must also make a
corresponding change to
`terraform/modules/ecs-service/config/otel_mapping_aws_prometheus.yml` in
`notifications-aws`.**
