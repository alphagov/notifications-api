FROM python:3.4-slim

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
		jq \

	&& echo "Install Cloud Foundry CLI" \
	&& curl -sSL "https://cli.run.pivotal.io/stable?release=debian64&source=github" -o /tmp/cloudfoundry-cli.deb \
	&& dpkg -i /tmp/cloudfoundry-cli.deb \
	&& cf install-plugin -r CF-Community -f "autopilot" \
	&& cf install-plugin -r CF-Community -f "blue-green-deploy" \
	&& cf install-plugin -r CF-Community -f "antifreeze" \

	&& echo "Clean up" \
	&& rm -rf /var/lib/apt/lists/* /tmp/*

RUN \
	echo "Install global pip packages" \
	&& pip install \
		virtualenv \
		awscli \
		wheel

WORKDIR /var/project
