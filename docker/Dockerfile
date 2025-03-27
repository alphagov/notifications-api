ARG UV_IMAGE_TAG=0.5.28  # auto-update
ARG DEBIAN_BASE_IMAGE_TAG=bookworm-20250317-slim  # auto-update
ARG UPDATED_SNAPSHOT_TIMESTAMP=20250325T000000Z  # auto-update
# SOURCE_DATE_EPOCH needs to be explicitly listed in build command to have desired effect, included
# here for reference
ARG SOURCE_DATE_EPOCH=1742169600  # auto-update: should match that of debian base image's original snapshot

FROM ghcr.io/astral-sh/uv:${UV_IMAGE_TAG} AS uv

######
FROM debian:${DEBIAN_BASE_IMAGE_TAG} AS base

SHELL ["/bin/bash", "-c"]

ARG SOURCE_DATE_EPOCH
ARG UPDATED_SNAPSHOT_TIMESTAMP

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}

RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  ! sed -E "/^# (http:.*snapshot.debian.org.*?)([0-9]{8}T[0-9]{6}Z)\$/q1" /etc/apt/sources.list.d/debian.sources; \
  sed -i -E "s/^# (http:.*snapshot.debian.org.*?)([0-9]{8}T[0-9]{6}Z)\$/URIs: \\1${UPDATED_SNAPSHOT_TIMESTAMP}/g" /etc/apt/sources.list.d/debian.sources; \
  ! sed -E "/^URIs: http:.*deb.debian.org.*$/q1" /etc/apt/sources.list.d/debian.sources > /dev/null; \
  sed -i -E "s/^URIs: http:.*deb.debian.org.*$/# \\0/g" /etc/apt/sources.list.d/debian.sources; \
  mkdir -p /etc/apt/apt.conf.d; \
  echo "Acquire::Check-Valid-Until false;" >> /etc/apt/apt.conf.d/10-nocheckvalid; \
  echo "Binary::apt::APT::Keep-Downloaded-Packages true;" >> /etc/apt/apt.conf.d/20-keepcache

RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  apt update; \
  apt upgrade; \
  apt install -y --no-install-recommends \
    ca-certificates \
    netbase \
    tzdata \
    libcurl4 \
    curl

COPY --from=uv /uv /uvx /bin/
ENV UV_CACHE_DIR="/tmp/uv-cache/"
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_INSTALLER_METADATA=1
ENV UV_PYTHON_INSTALL_DIR="/usr/local/python"

ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV="/opt/venv"
ENV PATH="${UV_PYTHON_INSTALL_DIR}/bin:${VIRTUAL_ENV}/bin:${PATH}"

COPY .python-version .
RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  echo "Installing python"; \
  uv python install

WORKDIR /home/vcap/app

##### Python Build Image #####################################################
FROM base AS python_build

ARG SOURCE_DATE_EPOCH

RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  echo "Install OS dependencies for python app requirements"; \
  apt update; \
  apt install -y --no-install-recommends \
    build-essential \
    git \
    libcurl4-openssl-dev \
    libssl-dev

COPY .python-version requirements.txt .

ENV CFLAGS="-frandom-seed=1234"

RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  echo "Installing python requirements"; \
  uv venv $VIRTUAL_ENV; \
  uv pip sync requirements.txt

COPY . .
RUN make generate-version-file  # This file gets copied across

##### Production Image #######################################################
FROM base AS production

RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  groupadd -r notify; \
  useradd -r -g notify notify; \
  chown -R notify:notify /home/vcap

USER notify

COPY --from=python_build --chown=root:root /opt/venv /opt/venv

COPY --chown=notify:notify app app
COPY --chown=notify:notify migrations migrations
COPY --chown=notify:notify templates templates
COPY --chown=notify:notify run_celery.py gunicorn_config.py application.py entrypoint.sh ./
COPY --from=python_build --chown=notify:notify /home/vcap/app/app/version.py app/version.py

RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  uv run -m compileall . -j1; \
  chown -R notify:notify /home/vcap/app; \
  chmod +x /home/vcap/app/entrypoint.sh

ENTRYPOINT [ "/home/vcap/app/entrypoint.sh" ]

##### Test Image ##############################################################
FROM production AS test

USER root
RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  echo "Install OS dependencies for test build"; \
  apt update; \
  apt install -y --no-install-recommends \
    sudo \
    make \
    curl \
    git; \
  usermod -aG sudo notify; \
  echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

USER notify

# Copying to overwrite is faster than RUN chown notify:notify ...
COPY --from=python_build --chown=notify:notify /opt/venv /opt/venv

# Install dev/test requirements
COPY --chown=notify:notify Makefile requirements_for_test.txt ./

RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  echo "Installing python requirements for test"; \
  uv pip sync requirements_for_test.txt

COPY --chown=notify:notify . .

##### Concourse Test Image ##############################################################
FROM test AS concourse_tests

ENV SQLALCHEMY_DATABASE_URI=postgresql://postgres:postgres@localhost/
ENV POSTGRES_VERSION=15
ENV POSTGRES_REPO_KEY=B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8

USER root
RUN --mount=type=tmpfs,target=/tmp \
    --mount=type=cache,target=/var/cache,sharing=private \
    --mount=type=cache,target=/var/lib/apt,sharing=private \
    --mount=type=tmpfs,target=/var/log \
  set -eux; \
  echo "Install postgresql dependencies"; \
  apt update; \
  apt install -y --no-install-recommends \
    gnupg \
    libcurl4-openssl-dev \
    libssl-dev \
    lsb-release

# Installation of postgres is based on https://github.com/docker-library/postgres/blob/0d0485cb02e526f5a240b7740b46c35404aaf13f/9.6/Dockerfile
# abandon hopes of reproducibility past this point

# Add the gpg key for postgresql package repository
RUN set -x \
    && export GNUPGHOME="$(mktemp -d)" \
    && gpg --batch --keyserver hkps://keyserver.ubuntu.com --recv-keys "$POSTGRES_REPO_KEY" \
    && gpg --batch --export "$POSTGRES_REPO_KEY" > /etc/apt/trusted.gpg.d/postgres.gpg \
    && command -v gpgconf > /dev/null && gpgconf --kill all \
    &&rm -rf "$GNUPGHOME" \
    && apt-key list

# Install postgres
RUN \
    echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main $POSTGRES_VERSION" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-$POSTGRES_VERSION \
    && rm -rf /var/lib/apt/lists/* /tmp/*

RUN \
    service postgresql start \
    && su - postgres -c "psql -c \"alter user postgres with password 'postgres';\""
