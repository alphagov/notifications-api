.DEFAULT_GOAL := help
SHELL := /bin/bash
DATE = $(shell date +%Y-%m-%d:%H:%M:%S)

APP_VERSION_FILE = app/version.py

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

VIRTUALENV_ROOT := $(shell [ -z $$VIRTUAL_ENV ] && echo $$(pwd)/venv || echo $$VIRTUAL_ENV)
PYTHON_EXECUTABLE_PREFIX := $(shell test -d "$${VIRTUALENV_ROOT}" && echo "$${VIRTUALENV_ROOT}/bin/" || echo "")


## DEVELOPMENT

.PHONY: bootstrap
bootstrap: generate-version-file ## Set up everything to run the app
	pip3 install -r requirements_for_test.txt
	createdb notification_api || true
	(. environment.sh && flask db upgrade) || true

.PHONY: bootstrap-with-docker
bootstrap-with-docker: generate-version-file ## Build the image to run the app in Docker
	docker build -f docker/Dockerfile --target test -t notifications-api .

.PHONY: run-flask
run-flask: ## Run flask
	. environment.sh && flask run -p 6011

.PHONY: run-flask-with-docker
run-flask-with-docker: ## Run flask
	./scripts/run_locally_with_docker.sh api-local

.PHONY: run-gunicorn-with-docker
run-gunicorn-with-docker: ## Run gunicorn
	./scripts/run_locally_with_docker.sh api

.PHONY: run-celery
run-celery: ## Run celery
	. environment.sh && celery \
		-A run_celery.notify_celery worker \
		--pidfile="/tmp/celery.pid" \
		--loglevel=INFO \
		--concurrency=4

.PHONY: run-celery-with-docker
run-celery-with-docker: ## Run celery in Docker container (useful if you can't install pycurl locally)
	./scripts/run_locally_with_docker.sh worker

.PHONY: run-celery-beat
run-celery-beat: ## Run celery beat
	. environment.sh && celery \
		-A run_celery.notify_celery beat \
		--loglevel=INFO

.PHONY: run-celery-beat-with-docker
run-celery-beat-with-docker: ## Run celery beat in Docker container (useful if you can't install pycurl locally)
	./scripts/run_locally_with_docker.sh celery-beat

.PHONY: run-migrations-with-docker
run-migrations-with-docker: ## Run alembic migrations in Docker container
	./scripts/run_locally_with_docker.sh migration

.PHONY: help
help:
	@cat $(MAKEFILE_LIST) | grep -E '^[a-zA-Z_-]+:.*?## .*$$' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: generate-version-file
generate-version-file: ## Generates the app version file
	@echo -e "__git_commit__ = \"${GIT_COMMIT}\"\n__time__ = \"${DATE}\"" > ${APP_VERSION_FILE}

.PHONY: drop-test-dbs
drop-test-dbs:
	@echo "Dropping test DBs."
	@for number in $$(seq 0 $$(python -c 'import os; print(os.cpu_count() - 1)')); do \
	    dropdb test_notification_api_gw$${number} --if-exists; \
	done
	@dropdb test_notification_api_master --if-exists
	@echo "Done."

.PHONY: drop-test-dbs-in-docker
drop-test-dbs-in-docker:
	@echo "Dropping test DBs in docker."
	@for number in $$(seq 0 $$(python -c 'import os; print(os.cpu_count() - 1)')); do \
	    PGUSER=notify PGPASSWORD=notify PGHOST=0.0.0.0 PGPORT=5433 dropdb test_notification_api_gw$${number} --if-exists; \
	done
	@PGUSER=notify PGPASSWORD=notify PGHOST=0.0.0.0 PGPORT=5433 dropdb test_notification_api_master --if-exists
	@echo "Done."

.PHONY: test
test: ## Run tests
	ruff check .
	black --check .
	pytest -n auto --maxfail=10

.PHONY: freeze-requirements
freeze-requirements: ## Pin all requirements including sub dependencies into requirements.txt
	pip install --upgrade pip-tools
	pip-compile requirements.in

.PHONY: bump-utils
bump-utils:  # Bump notifications-utils package to latest version
	${PYTHON_EXECUTABLE_PREFIX}python -c "from notifications_utils.version_tools import upgrade_version; upgrade_version()"

.PHONY: clean
clean:
	rm -rf node_modules cache target venv .coverage build tests/.cache ${CF_MANIFEST_PATH}


## DEPLOYMENT

.PHONY: preview
preview: ## Set environment to preview
	$(eval export DEPLOY_ENV=preview)
	$(eval export DNS_NAME="notify.works")
	@true

.PHONY: staging
staging: ## Set environment to staging
	$(eval export DEPLOY_ENV=staging)
	$(eval export DNS_NAME="staging-notify.works")
	@true

.PHONY: production
production: ## Set environment to production
	$(eval export DEPLOY_ENV=production)
	$(eval export DNS_NAME="notifications.service.gov.uk")
	@true

.PHONY: check-if-migrations-to-run
check-if-migrations-to-run:
	@echo $(shell API_HOST_NAME=https://api.${DNS_NAME} python3 scripts/check_if_new_migration.py)
