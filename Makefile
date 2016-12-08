.DEFAULT_GOAL := help
SHELL := /bin/bash
DATE = $(shell date +%Y-%m-%d:%H:%M:%S)

PIP_ACCEL_CACHE ?= ${CURDIR}/cache/pip-accel
APP_VERSION_FILE = app/version.py

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

DOCKER_IMAGE_TAG := $(shell cat docker/VERSION)
DOCKER_BUILDER_IMAGE_NAME = govuk/notify-api-builder:${DOCKER_IMAGE_TAG}

BUILD_TAG ?= notifications-api-manual
BUILD_NUMBER ?= 0
DEPLOY_BUILD_NUMBER ?= ${BUILD_NUMBER}
BUILD_URL ?=

DOCKER_CONTAINER_PREFIX = ${USER}-${BUILD_TAG}

CF_API ?= api.cloud.service.gov.uk
CF_ORG ?= govuk-notify
CF_SPACE ?= ${DEPLOY_ENV}

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
	$(if ${DNS_NAME},,$(error Must specify DNS_NAME))
	$(if ${AWS_ACCESS_KEY_ID},,$(error Must specify AWS_ACCESS_KEY_ID))
	$(if ${AWS_SECRET_ACCESS_KEY},,$(error Must specify AWS_SECRET_ACCESS_KEY))

.PHONY: sandbox
sandbox: ## Set environment to sandbox
	$(eval export DEPLOY_ENV=sandbox)
	$(eval export DNS_NAME="cloudapps.digital")
	@true

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
	. venv/bin/activate && PIP_ACCEL_CACHE=${PIP_ACCEL_CACHE} pip-accel install -r requirements_for_test.txt

.PHONY: generate-version-file
generate-version-file: ## Generates the app version file
	@echo -e "__travis_commit__ = \"${GIT_COMMIT}\"\n__time__ = \"${DATE}\"\n__travis_job_number__ = \"${BUILD_NUMBER}\"\n__travis_job_url__ = \"${BUILD_URL}\"" > ${APP_VERSION_FILE}

.PHONY: build
build: dependencies generate-version-file ## Build project
	. venv/bin/activate && PIP_ACCEL_CACHE=${PIP_ACCEL_CACHE} pip-accel wheel --wheel-dir=wheelhouse -r requirements.txt

.PHONY: cf-build
cf-build: dependencies generate-version-file ## Build project for PAAS

.PHONY: build-codedeploy-artifact
build-codedeploy-artifact: ## Build the deploy artifact for CodeDeploy
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
	aws s3 cp --region eu-west-1 --sse AES256 target/notifications-api.zip s3://${DNS_NAME}-codedeploy/notifications-api-${DEPLOY_BUILD_NUMBER}.zip
	aws s3 cp --region eu-west-1 --sse AES256 target/notifications-api-db-migration.zip s3://${DNS_NAME}-codedeploy/notifications-api-db-migration-${DEPLOY_BUILD_NUMBER}.zip

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
	. venv/bin/activate && coveralls

.PHONY: prepare-docker-build-image
prepare-docker-build-image: ## Prepare the Docker builder image
	mkdir -p ${PIP_ACCEL_CACHE}
	make -C docker build

.PHONY: build-with-docker
build-with-docker: prepare-docker-build-image ## Build inside a Docker container
	@docker run -i --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-build" \
		-v `pwd`:/var/project \
		-v ${PIP_ACCEL_CACHE}:/var/project/cache/pip-accel \
		-e GIT_COMMIT=${GIT_COMMIT} \
		-e BUILD_NUMBER=${BUILD_NUMBER} \
		-e BUILD_URL=${BUILD_URL} \
		-e http_proxy="${HTTP_PROXY}" \
		-e HTTP_PROXY="${HTTP_PROXY}" \
		-e https_proxy="${HTTPS_PROXY}" \
		-e HTTPS_PROXY="${HTTPS_PROXY}" \
		-e NO_PROXY="${NO_PROXY}" \
		${DOCKER_BUILDER_IMAGE_NAME} \
		make build

.PHONY: cf-build-with-docker
cf-build-with-docker: prepare-docker-build-image ## Build inside a Docker container
	@docker run -i --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-build" \
		-v "`pwd`:/var/project" \
		-v "${PIP_ACCEL_CACHE}:/var/project/cache/pip-accel" \
		-e GIT_COMMIT=${GIT_COMMIT} \
		-e BUILD_NUMBER=${BUILD_NUMBER} \
		-e BUILD_URL=${BUILD_URL} \
		-e http_proxy="${HTTP_PROXY}" \
		-e HTTP_PROXY="${HTTP_PROXY}" \
		-e https_proxy="${HTTPS_PROXY}" \
		-e HTTPS_PROXY="${HTTPS_PROXY}" \
		-e NO_PROXY="${NO_PROXY}" \
		${DOCKER_BUILDER_IMAGE_NAME} \
		make cf-build

.PHONY: test-with-docker
test-with-docker: prepare-docker-build-image create-docker-test-db ## Run tests inside a Docker container
	@docker run -i --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-test" \
		--link "${DOCKER_CONTAINER_PREFIX}-db:postgres" \
		-e TEST_DATABASE=postgresql://postgres:postgres@postgres/test_notification_api \
		-e GIT_COMMIT=${GIT_COMMIT} \
		-e BUILD_NUMBER=${BUILD_NUMBER} \
		-e BUILD_URL=${BUILD_URL} \
		-e http_proxy="${HTTP_PROXY}" \
		-e HTTP_PROXY="${HTTP_PROXY}" \
		-e https_proxy="${HTTPS_PROXY}" \
		-e HTTPS_PROXY="${HTTPS_PROXY}" \
		-e NO_PROXY="${NO_PROXY}" \
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
		-e http_proxy="${HTTP_PROXY}" \
		-e HTTP_PROXY="${HTTP_PROXY}" \
		-e https_proxy="${HTTPS_PROXY}" \
		-e HTTPS_PROXY="${HTTPS_PROXY}" \
		-e NO_PROXY="${NO_PROXY}" \
		${DOCKER_BUILDER_IMAGE_NAME} \
		make coverage

.PHONY: clean-docker-containers
clean-docker-containers: ## Clean up any remaining docker containers
	docker rm -f $(shell docker ps -q -f "name=${DOCKER_CONTAINER_PREFIX}") 2> /dev/null || true

.PHONY: clean
clean:
	rm -rf node_modules cache target venv .coverage build tests/.cache wheelhouse

.PHONY: cf-login
cf-login: ## Log in to Cloud Foundry
	$(if ${CF_USERNAME},,$(error Must specify CF_USERNAME))
	$(if ${CF_PASSWORD},,$(error Must specify CF_PASSWORD))
	$(if ${CF_SPACE},,$(error Must specify CF_SPACE))
	@echo "Logging in to Cloud Foundry on ${CF_API}"
	@cf login -a "${CF_API}" -u ${CF_USERNAME} -p "${CF_PASSWORD}" -o "${CF_ORG}" -s "${CF_SPACE}"

.PHONY: cf-deploy-api
cf-deploy-api: ## Deploys the API to Cloud Foundry
	$(eval export ORIG_INSTANCES=$(shell cf curl /v2/apps/$(shell cf app --guid notify-api) | jq -r ".entity.instances"))
	@echo "Original instance count: ${ORIG_INSTANCES}"
	cf check-manifest notify-api -f manifest-api-${CF_SPACE}.yml
	cf zero-downtime-push notify-api -f manifest-api-${CF_SPACE}.yml
	cf scale -i ${ORIG_INSTANCES} notify-api

.PHONY: cf-push-api
cf-push-api: ##
	cf push notify-api -f manifest-api-${CF_SPACE}.yml

.PHONY: cf-deploy-api-db-migration
cf-deploy-api-db-migration: ## Deploys the API db migration to Cloud Foundry
	cf check-manifest notify-api-db-migration -f manifest-api-db-migration.yml
	cf push notify-api-db-migration -f manifest-api-db-migration.yml

cf-push-api-db-migration: cf-deploy-api-db-migration ## Deploys the API db migration to Cloud Foundry

.PHONY: cf-deploy-delivery
cf-deploy-delivery: ## Deploys a delivery app to Cloud Foundry
	$(if ${CF_APP},,$(error Must specify CF_APP))
	$(eval export ORIG_INSTANCES=$(shell cf curl /v2/apps/$(shell cf app --guid ${CF_APP}) | jq -r ".entity.instances"))
	@echo "Original instance count: ${ORIG_INSTANCES}"
	cf check-manifest ${CF_APP} -f manifest-$(subst notify-,,${CF_APP}).yml
	cf zero-downtime-push ${CF_APP} -f manifest-$(subst notify-,,${CF_APP}).yml
	cf scale -i ${ORIG_INSTANCES} ${CF_APP}

.PHONY: cf-push-delivery
cf-push-delivery: ## Deploys a delivery app to Cloud Foundry
	$(if ${CF_APP},,$(error Must specify CF_APP))
	cf push ${CF_APP} -f manifest-$(subst notify-,,${CF_APP}).yml

define cf_deploy_with_docker
	@docker run -i --rm \
		--name "${DOCKER_CONTAINER_PREFIX}-${1}" \
		-v `pwd`:/var/project \
		-e http_proxy="${HTTP_PROXY}" \
		-e HTTP_PROXY="${HTTP_PROXY}" \
		-e https_proxy="${HTTPS_PROXY}" \
		-e HTTPS_PROXY="${HTTPS_PROXY}" \
		-e NO_PROXY="${NO_PROXY}" \
		-e CF_API="${CF_API}" \
		-e CF_USERNAME="${CF_USERNAME}" \
		-e CF_PASSWORD="${CF_PASSWORD}" \
		-e CF_ORG="${CF_ORG}" \
		-e CF_SPACE="${CF_SPACE}" \
		-e CF_APP="${CF_APP}" \
		${DOCKER_BUILDER_IMAGE_NAME} \
		${2}
endef

.PHONY: cf-deploy-api-with-docker
cf-deploy-api-with-docker: prepare-docker-build-image ## Deploys the API to Cloud Foundry from a Docker container
	$(call cf_deploy_with_docker,cf-deploy-api,make cf-login cf-deploy-api)

.PHONY: cf-deploy-api-db-migration-with-docker
cf-deploy-api-db-migration-with-docker: prepare-docker-build-image ## Deploys the API db migration to Cloud Foundry from a Docker container
	$(call cf_deploy_with_docker,cf-deploy-api-db-migration,make cf-login cf-deploy-api-db-migration)

.PHONY: cf-deploy-delivery-with-docker
cf-deploy-delivery-with-docker: prepare-docker-build-image ## Deploys a delivery app to Cloud Foundry from a Docker container
	$(if ${CF_APP},,$(error Must specify CF_APP))
	$(call cf_deploy_with_docker,cf-deploy-delivery-${CF_APP},make cf-login cf-deploy-delivery)
