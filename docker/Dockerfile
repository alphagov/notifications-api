FROM python:3.6-slim

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV PYTHONUNBUFFERED=1 \
	DEBIAN_FRONTEND=noninteractive

RUN \
	echo "Install base packages" \
	&& ([ -z "$HTTP_PROXY" ] || echo "Acquire::http::Proxy \"${HTTP_PROXY}\";" > /etc/apt/apt.conf.d/99HttpProxy) \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		make \
		curl \
		git \
		build-essential \
		zip \
		libpq-dev \
	&& echo "Clean up" \
	&& rm -rf /var/lib/apt/lists/* /tmp/*

RUN \
	echo "Install Cloud Foundry CLI" \
	&& curl -sSL "https://cli.run.pivotal.io/stable?release=debian64&source=github" -o /tmp/cloudfoundry-cli.deb \
	&& dpkg -i /tmp/cloudfoundry-cli.deb

# these are declared statically here so that they're cached by the docker image - if we run after the `COPY` command
# they won't be cached so it'll re-download every time. But these don't involve the filesystem
COPY requirements.txt .
COPY requirements_for_test.txt .
RUN \
	echo "Installing python dependencies" \
	&& pip install -r requirements_for_test.txt

WORKDIR /var/project

COPY . .
