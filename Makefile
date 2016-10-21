.DEFAULT_GOAL := help
SHELL := /bin/bash
DATE = $(shell date +%Y-%m-%d:%H:%M:%S)

PIP_ACCEL_CACHE ?= ${CURDIR}/cache/pip-accel
APP_VERSION_FILE = app/version.py

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

DOCKER_BUILDER_IMAGE_NAME = govuk/notify-api-builder

BUILD_TAG ?= notifications-api-manual
BUILD_NUMBER ?= 0
DEPLOY_BUILD_NUMBER ?= ${BUILD_NUMBER}
BUILD_URL ?=

DOCKER_CONTAINER_PREFIX = ${USER}-${BUILD_TAG}

.PHONY: help
help:
	@cat $(MAKEFILE_LIST) | grep -E '^[a-zA-Z_-]+:.*?## .*$$' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: venv
venv: venv/bin/activate ## Create virtualenv if it does not exist

venv/bin/activate:
	test -d venv || virtualenv venv
	./venv/bin/pip install pip-accel

.PHONY: check-env-vars
check-env-vars: ## Check mandatory environment variables
	$(if ${DEPLOY_ENV},,$(error Must specify DEPLOY_ENV))
	$(if ${DNS_NAME},,$(error Must specify DNS_NAME))
	$(if ${AWS_ACCESS_KEY_ID},,$(error Must specify AWS_ACCESS_KEY_ID))
	$(if ${AWS_SECRET_ACCESS_KEY},,$(error Must specify AWS_SECRET_ACCESS_KEY))

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

.PHONY: dependencies
dependencies: venv ## Install build dependencies
	mkdir -p ${PIP_ACCEL_CACHE}
	PIP_ACCEL_CACHE=${PIP_ACCEL_CACHE} ./venv/bin/pip-accel install -r requirements_for_test.txt

.PHONY: generate-version-file
generate-version-file: ## Generates the app version file
	@echo -e "__travis_commit__ = \"${GIT_COMMIT}\"\n__time__ = \"${DATE}\"\n__travis_job_number__ = \"${BUILD_NUMBER}\"\n__travis_job_url__ = \"${BUILD_URL}\"" > ${APP_VERSION_FILE}

.PHONY: build
build: dependencies generate-version-file ## Build project

.PHONY: build-codedeploy-artifact
build-codedeploy-artifact: ## Build the deploy artifact for CodeDeploy
	pip3 wheel --wheel-dir=wheelhouse -r requirements.txt
	mkdir -p target
	zip -r -x@deploy-exclude.lst target/notifications-api.zip *

	rm -rf build/db-migration-codedeploy
	mkdir -p build/db-migration-codedeploy
	unzip target/notifications-api.zip -d build/db-migration-codedeploy
	cd build/db-migration-codedeploy && \
		mv -f appspec-db-migration.yml appspec.yml && \
		zip -r -x@deploy-exclude.lst ../../target/notifications-api-db-migration.zip *

.PHONY: upload-codedeploy-artifact ## Upload the deploy artifact for CodeDeploy
upload-codedeploy-artifact: check-env-vars
	aws s3 cp --region eu-west-1 target/notifications-api.zip s3://${DNS_NAME}-codedeploy/notifications-api-${DEPLOY_BUILD_NUMBER}.zip
	aws s3 cp --region eu-west-1 target/notifications-api-db-migration.zip s3://${DNS_NAME}-codedeploy/notifications-api-db-migration-${DEPLOY_BUILD_NUMBER}.zip

.PHONY: test
test: venv generate-version-file ## Run tests
	./scripts/run_tests.sh

.PHONY: deploy-api
deploy-api: check-env-vars ## Trigger CodeDeploy for the api
	aws deploy create-deployment --application-name notify-api --deployment-config-name CodeDeployDefault.OneAtATime --deployment-group-name notify-api --s3-location bucket=${DNS_NAME}-codedeploy,key=notifications-api-${DEPLOY_BUILD_NUMBER}.zip,bundleType=zip --region eu-west-1

.PHONY: deploy-api
deploy-api-db-migration: check-env-vars ## Trigger CodeDeploy for the api db migration
	aws deploy create-deployment --application-name notify-api-db-migration --deployment-config-name CodeDeployDefault.OneAtATime --deployment-group-name notify-api-db-migration --s3-location bucket=${DNS_NAME}-codedeploy,key=notifications-api-db-migration-${DEPLOY_BUILD_NUMBER}.zip,bundleType=zip --region eu-west-1

.PHONY: deploy-admin-api
deploy-admin-api: check-env-vars ## Trigger CodeDeploy for the admin api
	aws deploy create-deployment --application-name notify-admin-api --deployment-config-name CodeDeployDefault.OneAtATime --deployment-group-name notify-admin-api --s3-location bucket=${DNS_NAME}-codedeploy,key=notifications-api-${DEPLOY_BUILD_NUMBER}.zip,bundleType=zip --region eu-west-1

.PHONY: deploy-delivery
deploy-delivery: check-env-vars ## Trigger CodeDeploy for the delivery app
	aws deploy create-deployment --application-name notify-delivery --deployment-config-name CodeDeployDefault.OneAtATime --deployment-group-name notify-delivery --s3-location bucket=${DNS_NAME}-codedeploy,key=notifications-api-${DEPLOY_BUILD_NUMBER}.zip,bundleType=zip --region eu-west-1

.PHONY: coverage
coverage: venv ## Create coverage report
	./venv/bin/coveralls

.PHONY: prepare-docker-build-image
prepare-docker-build-image: ## Prepare the Docker builder image
	mkdir -p ${PIP_ACCEL_CACHE}
	make -C docker build-build-image

.PHONY: build-with-docker
build-with-docker: prepare-docker-build-image ## Build inside a Docker container
	@docker run -i --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-build" \
		-v `pwd`:/var/project \
		-v ${PIP_ACCEL_CACHE}:/var/project/cache/pip-accel \
		-e GIT_COMMIT=${GIT_COMMIT} \
		-e BUILD_NUMBER=${BUILD_NUMBER} \
		-e BUILD_URL=${BUILD_URL} \
		${DOCKER_BUILDER_IMAGE_NAME} \
		make build

.PHONY: test-with-docker
test-with-docker: prepare-docker-build-image create-docker-test-db ## Run tests inside a Docker container
	@docker run -i --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-test" \
		--link "${DOCKER_CONTAINER_PREFIX}-db:postgres" \
		-e TEST_DATABASE=postgresql://postgres:postgres@postgres/test_notification_api \
		-e GIT_COMMIT=${GIT_COMMIT} \
		-e BUILD_NUMBER=${BUILD_NUMBER} \
		-e BUILD_URL=${BUILD_URL} \
		-v `pwd`:/var/project \
		${DOCKER_BUILDER_IMAGE_NAME} \
		make test

.PHONY: test-with-docker
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
	@docker run -i --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-coverage" \
		-v `pwd`:/var/project \
		-e COVERALLS_REPO_TOKEN=${COVERALLS_REPO_TOKEN} \
		-e CIRCLECI=1 \
		-e CI_NAME=${CI_NAME} \
		-e CI_BUILD_NUMBER=${BUILD_NUMBER} \
		-e CI_BUILD_URL=${BUILD_URL} \
		-e CI_BRANCH=${GIT_BRANCH} \
		-e CI_PULL_REQUEST=${CI_PULL_REQUEST} \
		${DOCKER_BUILDER_IMAGE_NAME} \
		make coverage

.PHONY: clean-docker-containers
clean-docker-containers: ## Clean up any remaining docker containers
	docker rm -f $(shell docker ps -q -f "name=${DOCKER_CONTAINER_PREFIX}") 2> /dev/null || true

clean:
	rm -rf node_modules cache target venv .coverage build tests/.cache
