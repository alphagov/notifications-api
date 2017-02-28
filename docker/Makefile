.DEFAULT_GOAL := help
SHELL := /bin/bash
DOCKER_IMAGE_TAG := $(shell cat VERSION)

.PHONY: help
help:
	@cat $(MAKEFILE_LIST) | grep -E '^[a-zA-Z_-]+:.*?## .*$$' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build:
	docker pull `grep "FROM " Dockerfile | cut -d ' ' -f 2` || true
	docker build \
		--build-arg HTTP_PROXY="${HTTP_PROXY}" \
		--build-arg HTTPS_PROXY="${HTTP_PROXY}" \
		--build-arg NO_PROXY="${NO_PROXY}" \
		-t govuk/notify-api-builder:${DOCKER_IMAGE_TAG} \
		.

.PHONY: bash
bash:
	docker run -it --rm \
		-e UID=$(shell id -u) \
		-e GID=$(shell id -g) \
		govuk/notify-api-builder:${DOCKER_IMAGE_TAG} \
		bash

.PHONY: bash
bash-hostuser:
	docker run -it --rm \
		-e UID=$(shell id -u) \
		-e GID=$(shell id -g) \
		govuk/notify-api-builder:${DOCKER_IMAGE_TAG} \
		gosu hostuser bash
