.DEFAULT_GOAL := help
SHELL := /bin/bash
DATE = $(shell date +%Y-%m-%d:%H:%M:%S)

APP_VERSION_FILE = app/version.py

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

CF_API ?= api.cloud.service.gov.uk
CF_ORG ?= govuk-notify
CF_SPACE ?= ${DEPLOY_ENV}
CF_HOME ?= ${HOME}
$(eval export CF_HOME)

CF_MANIFEST_PATH ?= /tmp/manifest.yml


NOTIFY_CREDENTIALS ?= ~/.notify-credentials

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
	./scripts/run_locally_with_docker.sh beat

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

.PHONY: cf-login
cf-login: ## Log in to Cloud Foundry
	$(if ${CF_USERNAME},,$(error Must specify CF_USERNAME))
	$(if ${CF_PASSWORD},,$(error Must specify CF_PASSWORD))
	$(if ${CF_SPACE},,$(error Must specify CF_SPACE))
	@echo "Logging in to Cloud Foundry on ${CF_API}"
	@cf login -a "${CF_API}" -u ${CF_USERNAME} -p "${CF_PASSWORD}" -o "${CF_ORG}" -s "${CF_SPACE}"

.PHONY: generate-manifest
generate-manifest:
	$(if ${CF_APP},,$(error Must specify CF_APP))
	$(if ${CF_SPACE},,$(error Must specify CF_SPACE))
	$(if $(shell which gpg2), $(eval export GPG=gpg2), $(eval export GPG=gpg))
	$(if ${GPG_PASSPHRASE_TXT}, $(eval export DECRYPT_CMD=echo -n $$$${GPG_PASSPHRASE_TXT} | ${GPG} --quiet --batch --passphrase-fd 0 --pinentry-mode loopback -d), $(eval export DECRYPT_CMD=${GPG} --quiet --batch -d))

	@jinja2 --strict manifest.yml.j2 \
	    -D environment=${CF_SPACE} \
	    -D CF_APP=${CF_APP} \
	    --format=yaml \
	    <(${DECRYPT_CMD} ${NOTIFY_CREDENTIALS}/credentials/${CF_SPACE}/paas/environment-variables.gpg) 2>&1

.PHONY: cf-deploy
cf-deploy: ## Deploys the app to Cloud Foundry
	$(if ${CF_SPACE},,$(error Must specify CF_SPACE))
	$(if ${CF_APP},,$(error Must specify CF_APP))
	cf target -o ${CF_ORG} -s ${CF_SPACE}
	@cf app --guid ${CF_APP} || exit 1

	# cancel any existing deploys to ensure we can apply manifest (if a deploy is in progress you'll see ScaleDisabledDuringDeployment)
	cf cancel-deployment ${CF_APP} || true

	# generate manifest (including secrets) and write it to CF_MANIFEST_PATH (in /tmp/)
	make -s CF_APP=${CF_APP} generate-manifest > ${CF_MANIFEST_PATH}

	$(if ${USE_DROPLETS},CF_APP=${CF_APP} CF_MANIFEST_PATH=${CF_MANIFEST_PATH} ./scripts/deploy.sh,CF_STARTUP_TIMEOUT=15 cf push ${CF_APP} --strategy=rolling -f ${CF_MANIFEST_PATH})
	# delete old manifest file
	rm ${CF_MANIFEST_PATH}

.PHONY: cf-deploy-api-db-migration
cf-deploy-api-db-migration:
	$(if ${CF_SPACE},,$(error Must specify CF_SPACE))
	cf target -o ${CF_ORG} -s ${CF_SPACE}
	make -s CF_APP=notify-api-db-migration generate-manifest > ${CF_MANIFEST_PATH}

	$(if ${USE_DROPLETS},CF_APP=notify-api-db-migration CF_MANIFEST_PATH=${CF_MANIFEST_PATH} ./scripts/deploy.sh,CF_STARTUP_TIMEOUT=15 cf push ${CF_APP} --no-route -f ${CF_MANIFEST_PATH})
	rm ${CF_MANIFEST_PATH}

	cf run-task notify-api-db-migration --command="flask db upgrade" --name api_db_migration

.PHONY: cf-check-api-db-migration-task
cf-check-api-db-migration-task: ## Get the status for the last notify-api-db-migration task
	@cf curl /v3/apps/`cf app --guid notify-api-db-migration`/tasks?order_by=-created_at | jq -r ".resources[0].state"

.PHONY: cf-rollback
cf-rollback: ## Rollbacks the app to the previous release
	$(if ${CF_APP},,$(error Must specify CF_APP))
	rm ${CF_MANIFEST_PATH}
	cf cancel-deployment ${CF_APP}

.PHONY: check-if-migrations-to-run
check-if-migrations-to-run:
	@echo $(shell python3 scripts/check_if_new_migration.py)

.PHONY: cf-deploy-failwhale
cf-deploy-failwhale:
	$(if ${CF_SPACE},,$(error Must target space, eg `make preview cf-deploy-failwhale`))
	cd ./paas-failwhale; cf push notify-api-failwhale -f manifest.yml

.PHONY: enable-failwhale
enable-failwhale: ## Enable the failwhale app and disable api
	$(if ${DNS_NAME},,$(error Must target space, eg `make preview enable-failwhale`))
	# make sure failwhale is running first
	cf start notify-api-failwhale

	cf map-route notify-api-failwhale ${DNS_NAME} --hostname api
	cf unmap-route notify-api ${DNS_NAME} --hostname api
	@echo "Failwhale is enabled"

.PHONY: disable-failwhale
disable-failwhale: ## Disable the failwhale app and enable api
	$(if ${DNS_NAME},,$(error Must target space, eg `make preview disable-failwhale`))

	cf map-route notify-api ${DNS_NAME} --hostname api
	cf unmap-route notify-api-failwhale ${DNS_NAME} --hostname api
	cf stop notify-api-failwhale
	@echo "Failwhale is disabled"
