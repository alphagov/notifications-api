FROM python:3.13-slim-bookworm AS base

COPY --from=ghcr.io/astral-sh/uv:0.5.28 /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV VIRTUAL_ENV="/opt/venv"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    procps \
    libcurl4 \
    curl \
    && apt-get -y clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*

WORKDIR /home/vcap/app

##### Python Build Image #####################################################
FROM base AS python_build

RUN echo "Install OS dependencies for python app requirements" &&  \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libcurl4-openssl-dev \
    libssl-dev && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*

COPY requirements.txt .

ENV UV_CACHE_DIR='/tmp/uv-cache/'
RUN echo "Installing python requirements" && \
    python3 -m venv /opt/venv && \
    uv pip sync --python /opt/venv/bin/python requirements.txt

COPY . .
RUN make generate-version-file  # This file gets copied across

##### Production Image #######################################################
FROM base AS production

# Temporarily switch to root to install sudo
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends sudo && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*

# Create user and add to sudo group
RUN groupadd -r notify && useradd -r -g notify notify && chown -R notify:notify /home/vcap
RUN usermod -aG sudo notify && \
    echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# Switch back to the non-root user
USER notify

RUN mkdir /home/vcap/logs

COPY --from=python_build --chown=root:root /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY --chown=notify:notify app app
COPY --chown=notify:notify migrations migrations
COPY --chown=notify:notify templates templates
COPY --chown=notify:notify run_celery.py gunicorn_config.py application.py entrypoint.sh run_and_upload_profile.sh ./
COPY --from=python_build --chown=notify:notify /home/vcap/app/app/version.py app/version.py

RUN python -m compileall . && \
    chown -R notify:notify /home/vcap/app && \
    chmod +x /home/vcap/app/entrypoint.sh && \
    chmod +x /home/vcap/app/run_and_upload_profile.sh

ENTRYPOINT [ "/home/vcap/app/entrypoint.sh" ]

##### Test Image ##############################################################
FROM production AS test

USER root
RUN echo "Install OS dependencies for test build" && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      sudo \
      make \
      curl \
      git && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*
RUN usermod -aG sudo notify
RUN echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
USER notify

# Make sure the app/ directory is there so that "make bootstrap" can create app/version.py
RUN mkdir -p app

# Copying to overwrite is faster than RUN chown notify:notify ...
COPY --from=python_build --chown=notify:notify /opt/venv /opt/venv

# Install dev/test requirements
COPY --chown=notify:notify Makefile requirements_for_test.txt ./
ENV UV_CACHE_DIR='/tmp/uv-cache/'
RUN make bootstrap

COPY --chown=notify:notify . .

##### Concourse Test Image ##############################################################
FROM production AS concourse_tests

SHELL ["/bin/bash", "-c"]

USER root
RUN echo "Install OS dependencies for test build" && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      sudo \
      libcurl4-openssl-dev \
      libssl-dev \
      make \
      git && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*
RUN usermod -aG sudo notify
RUN echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
USER notify

# Make sure the app/ directory is there so that "make bootstrap" can create app/version.py
RUN mkdir -p app

# Copying to overwrite is faster than RUN chown notify:notify ...
COPY --from=python_build --chown=notify:notify /opt/venv /opt/venv

# Install dev/test requirements
COPY --from=python_build --chown=notify:notify /home/vcap/app/app/version.py app/version.py
COPY --chown=notify:notify . .

ENV SQLALCHEMY_DATABASE_URI=postgresql://postgres:postgres@localhost/

ENV UV_CACHE_DIR='/tmp/uv-cache/'
RUN uv pip sync requirements_for_test.txt

USER root

ENV POSTGRES_VERSION=15 \
    POSTGRES_REPO_KEY=B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8

RUN \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        gnupg \
        lsb-release

# Installation of postgres is based on https://github.com/docker-library/postgres/blob/0d0485cb02e526f5a240b7740b46c35404aaf13f/9.6/Dockerfile

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
