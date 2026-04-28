This module was named `otel_metrics` so it wouldn't conflict with the `metrics`
field in `app/__init__.py`.

Once we've migrated away from the GDS metrics lib entirely we can rename this
module to simply `metrics`.
