.DEFAULT_GOAL := help
SHELL := /bin/bash
DATE = $(shell date +%Y-%m-%d:%H:%M:%S)

PIP_ACCEL_CACHE ?= ${CURDIR}/cache/pip-accel
APP_VERSION_FILE = app/version.py

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

DOCKER_IMAGE_TAG := $(shell cat docker/VERSION)
DOCKER_BUILDER_IMAGE_NAME = govuk/notify-api-builder:${DOCKER_IMAGE_TAG}
DOCKER_TTY ?= $(if ${JENKINS_HOME},,t)

BUILD_TAG ?= notifications-api-manual
BUILD_NUMBER ?= 0
DEPLOY_BUILD_NUMBER ?= ${BUILD_NUMBER}
BUILD_URL ?=

DOCKER_CONTAINER_PREFIX = ${USER}-${BUILD_TAG}

CF_API ?= api.cloud.service.gov.uk
CF_ORG ?= govuk-notify
CF_SPACE ?= ${DEPLOY_ENV}
CF_HOME ?= ${HOME}
$(eval export CF_HOME)

CF_MANIFEST_FILE = manifest-$(firstword $(subst -, ,$(subst notify-,,${CF_APP})))-${CF_SPACE}.yml

NOTIFY_CREDENTIALS ?= ~/.notify-credentials

.PHONY: help
help:
	@cat $(MAKEFILE_LIST) | grep -E '^[a-zA-Z_-]+:.*?## .*$$' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: venv
venv: venv/bin/activate ## Create virtualenv if it does not exist

venv/bin/activate:
	test -d venv || virtualenv venv -p python3
	. venv/bin/activate && pip install pip-accel

.PHONY: check-env-vars
check-env-vars: ## Check mandatory environment variables
	$(if ${DEPLOY_ENV},,$(error Must specify DEPLOY_ENV))

.PHONY: sandbox
sandbox: ## Set environment to sandbox
	$(eval export DEPLOY_ENV=sandbox)
	@true

.PHONY: preview
preview: ## Set environment to preview
	$(eval export DEPLOY_ENV=preview)
	@true

.PHONY: staging
staging: ## Set environment to staging
	$(eval export DEPLOY_ENV=staging)
	@true

.PHONY: production
production: ## Set environment to production
	$(eval export DEPLOY_ENV=production)
	@true

.PHONY: dependencies
dependencies: venv ## Install build dependencies
	mkdir -p ${PIP_ACCEL_CACHE}
	. venv/bin/activate && PIP_ACCEL_CACHE=${PIP_ACCEL_CACHE} pip-accel install -r requirements_for_test.txt

.PHONY: generate-version-file
generate-version-file: ## Generates the app version file
	@echo -e "__travis_commit__ = \"${GIT_COMMIT}\"\n__time__ = \"${DATE}\"\n__travis_job_number__ = \"${BUILD_NUMBER}\"\n__travis_job_url__ = \"${BUILD_URL}\"" > ${APP_VERSION_FILE}

.PHONY: build
build: dependencies generate-version-file ## Build project
	. venv/bin/activate && PIP_ACCEL_CACHE=${PIP_ACCEL_CACHE} pip-accel install -r requirements.txt

.PHONY: build-paas-artifact
build-paas-artifact:  ## Build the deploy artifact for PaaS
	rm -rf target
	mkdir -p target
	zip -y -q -r -x@deploy-exclude.lst target/notifications-api.zip ./

.PHONY: upload-paas-artifact ## Upload the deploy artifact for PaaS
upload-paas-artifact:
	$(if ${DEPLOY_BUILD_NUMBER},,$(error Must specify DEPLOY_BUILD_NUMBER))
	$(if ${JENKINS_S3_BUCKET},,$(error Must specify JENKINS_S3_BUCKET))
	aws s3 cp --region eu-west-1 --sse AES256 target/notifications-api.zip s3://${JENKINS_S3_BUCKET}/build/notifications-api/${DEPLOY_BUILD_NUMBER}.zip

.PHONY: test
test: venv generate-version-file ## Run tests
	./scripts/run_tests.sh

.PHONY: coverage
coverage: venv ## Create coverage report
	. venv/bin/activate && coveralls

.PHONY: prepare-docker-build-image
prepare-docker-build-image: ## Prepare the Docker builder image
	mkdir -p ${PIP_ACCEL_CACHE}
	make -C docker build

.PHONY: build-with-docker
build-with-docker: prepare-docker-build-image ## Build inside a Docker container
	@docker run -i${DOCKER_TTY} --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-build" \
		-v "`pwd`:/var/project" \
		-v "${PIP_ACCEL_CACHE}:/var/project/cache/pip-accel" \
		-e UID=$(shell id -u) \
		-e GID=$(shell id -g) \
		-e GIT_COMMIT=${GIT_COMMIT} \
		-e BUILD_NUMBER=${BUILD_NUMBER} \
		-e BUILD_URL=${BUILD_URL} \
		-e http_proxy="${HTTP_PROXY}" \
		-e HTTP_PROXY="${HTTP_PROXY}" \
		-e https_proxy="${HTTPS_PROXY}" \
		-e HTTPS_PROXY="${HTTPS_PROXY}" \
		-e NO_PROXY="${NO_PROXY}" \
		${DOCKER_BUILDER_IMAGE_NAME} \
		gosu hostuser make build

.PHONY: test-with-docker
test-with-docker: prepare-docker-build-image create-docker-test-db ## Run tests inside a Docker container
	@docker run -i${DOCKER_TTY} --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-test" \
		--link "${DOCKER_CONTAINER_PREFIX}-db:postgres" \
		-e UID=$(shell id -u) \
		-e GID=$(shell id -g) \
		-e SQLALCHEMY_DATABASE_URI=postgresql://postgres:postgres@postgres/test_notification_api \
		-e GIT_COMMIT=${GIT_COMMIT} \
		-e BUILD_NUMBER=${BUILD_NUMBER} \
		-e BUILD_URL=${BUILD_URL} \
		-e http_proxy="${HTTP_PROXY}" \
		-e HTTP_PROXY="${HTTP_PROXY}" \
		-e https_proxy="${HTTPS_PROXY}" \
		-e HTTPS_PROXY="${HTTPS_PROXY}" \
		-e NO_PROXY="${NO_PROXY}" \
		-v "`pwd`:/var/project" \
		${DOCKER_BUILDER_IMAGE_NAME} \
		gosu hostuser make test

.PHONY: create-docker-test-db
create-docker-test-db: ## Start the test database in a Docker container
	docker rm -f ${DOCKER_CONTAINER_PREFIX}-db 2> /dev/null || true
	@docker run -d \
		--name "${DOCKER_CONTAINER_PREFIX}-db" \
		-e POSTGRES_PASSWORD="postgres" \
		-e POSTGRES_DB=test_notification_api \
		postgres:9.5
	sleep 3

# FIXME: CIRCLECI=1 is an ugly hack because the coveralls-python library sends the PR link only this way
.PHONY: coverage-with-docker
coverage-with-docker: prepare-docker-build-image ## Generates coverage report inside a Docker container
	@docker run -i${DOCKER_TTY} --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-coverage" \
		-v "`pwd`:/var/project" \
		-e UID=$(shell id -u) \
		-e GID=$(shell id -g) \
		-e COVERALLS_REPO_TOKEN=${COVERALLS_REPO_TOKEN} \
		-e CIRCLECI=1 \
		-e CI_NAME=${CI_NAME} \
		-e CI_BUILD_NUMBER=${BUILD_NUMBER} \
		-e CI_BUILD_URL=${BUILD_URL} \
		-e CI_BRANCH=${GIT_BRANCH} \
		-e CI_PULL_REQUEST=${CI_PULL_REQUEST} \
		-e http_proxy="${HTTP_PROXY}" \
		-e HTTP_PROXY="${HTTP_PROXY}" \
		-e https_proxy="${HTTPS_PROXY}" \
		-e HTTPS_PROXY="${HTTPS_PROXY}" \
		-e NO_PROXY="${NO_PROXY}" \
		${DOCKER_BUILDER_IMAGE_NAME} \
		gosu hostuser make coverage

.PHONY: clean-docker-containers
clean-docker-containers: ## Clean up any remaining docker containers
	docker rm -f $(shell docker ps -q -f "name=${DOCKER_CONTAINER_PREFIX}") 2> /dev/null || true

.PHONY: clean
clean:
	rm -rf node_modules cache target venv .coverage build tests/.cache

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

	@./scripts/generate_manifest.py ${CF_MANIFEST_FILE} \
	    <(${DECRYPT_CMD} ${NOTIFY_CREDENTIALS}/credentials/${CF_SPACE}/paas/environment-variables.gpg)

.PHONY: cf-deploy
cf-deploy: ## Deploys the app to Cloud Foundry
	$(if ${CF_SPACE},,$(error Must specify CF_SPACE))
	$(if ${CF_APP},,$(error Must specify CF_APP))
	@cf app --guid ${CF_APP} || exit 1
	cf rename ${CF_APP} ${CF_APP}-rollback
	cf push ${CF_APP} -f <(make -s generate-manifest)
	cf scale -i $$(cf curl /v2/apps/$$(cf app --guid ${CF_APP}-rollback) | jq -r ".entity.instances" 2>/dev/null || echo "1") ${CF_APP}
	cf stop ${CF_APP}-rollback
	# sleep for 10 seconds to try and make sure that all worker threads (either web api or celery) have finished before we delete
	# when we delete the DB is unbound from the app, which can cause "permission denied for relation" psycopg2 errors.
	sleep 10

	# get the new GUID, and find all crash events for that. If there were any crashes we will abort the deploy.
	[ $$(cf curl "/v2/events?q=type:app.crash&q=actee:$$(cf app --guid ${CF_APP})" | jq ".total_results") -eq 0 ]
	cf delete -f ${CF_APP}-rollback

.PHONY: cf-deploy-api-db-migration
cf-deploy-api-db-migration:
	$(if ${CF_SPACE},,$(error Must specify CF_SPACE))
	cf unbind-service notify-api-db-migration notify-db
	cf unbind-service notify-api-db-migration notify-config
	cf unbind-service notify-api-db-migration notify-aws
	cf push notify-api-db-migration -f <(make -s CF_APP=api generate-manifest)
	cf run-task notify-api-db-migration "flask db upgrade" --name api_db_migration

.PHONY: cf-check-api-db-migration-task
cf-check-api-db-migration-task: ## Get the status for the last notify-api-db-migration task
	@cf curl /v3/apps/`cf app --guid notify-api-db-migration`/tasks?order_by=-created_at | jq -r ".resources[0].state"

.PHONY: cf-rollback
cf-rollback: ## Rollbacks the app to the previous release
	$(if ${CF_APP},,$(error Must specify CF_APP))
	@cf app --guid ${CF_APP}-rollback || exit 1
	@[ $$(cf curl /v2/apps/`cf app --guid ${CF_APP}-rollback` | jq -r ".entity.state") = "STARTED" ] || (echo "Error: rollback is not possible because ${CF_APP}-rollback is not in a started state" && exit 1)
	cf delete -f ${CF_APP} || true
	cf rename ${CF_APP}-rollback ${CF_APP}

.PHONY: cf-push
cf-push:
	$(if ${CF_APP},,$(error Must specify CF_APP))
	cf target -o ${CF_ORG} -s ${CF_SPACE}
	cf push ${CF_APP} -f <(make -s generate-manifest)

.PHONY: check-if-migrations-to-run
check-if-migrations-to-run:
	@echo $(shell python3 scripts/check_if_new_migration.py)
