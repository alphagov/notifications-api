FROM python:3.13-slim-bookworm AS base

COPY --from=ghcr.io/astral-sh/uv:0.5.28 /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV VIRTUAL_ENV="/opt/venv"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
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

# build context is `..`, so requirements lives under notifications-api/
COPY notifications-api/requirements.txt .

# local kombu must exist during build for file:///home/vcap/kombu
COPY kombu/ /home/vcap/kombu/

ENV UV_CACHE_DIR='/tmp/uv-cache/'
RUN echo "Installing python requirements" && \
    python3 -m venv /opt/venv && \
    uv pip sync --python /opt/venv/bin/python requirements.txt

# copy the notifications-api repo contents into the image
COPY notifications-api/ .
RUN make generate-version-file  # This file gets copied across

##### Production Image #######################################################
FROM base AS production

RUN groupadd -r notify && useradd -r -g notify notify && chown -R notify:notify /home/vcap
USER notify

RUN mkdir /home/vcap/logs

COPY --from=python_build --chown=root:root /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# build context is `..`, so these live under notifications-api/
COPY --chown=notify:notify notifications-api/app app
COPY --chown=notify:notify notifications-api/migrations migrations
COPY --chown=notify:notify notifications-api/templates templates
COPY --chown=notify:notify \
  notifications-api/run_celery.py \
  notifications-api/gunicorn_config.py \
  notifications-api/application.py \
  notifications-api/entrypoint.sh \
  ./

COPY --from=python_build --chown=notify:notify /home/vcap/app/app/version.py app/version.py

RUN python -m compileall . && \
    chown -R notify:notify /home/vcap/app && \
    chmod +x /home/vcap/app/entrypoint.sh

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

# Install dev/test requirements (these files live under notifications-api/)
COPY --chown=notify:notify notifications-api/Makefile notifications-api/requirements_for_test.txt ./

# ✅ Ensure file:///home/vcap/kombu exists when bootstrap installs requirements_for_test.txt
COPY --from=python_build --chown=notify:notify /home/vcap/kombu /home/vcap/kombu

ENV UV_CACHE_DIR='/tmp/uv-cache/'
RUN make bootstrap

# Copy the full notifications-api repo contents into test image
COPY --chown=notify:notify notifications-api/ .

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

# ✅ Ensure file:///home/vcap/kombu exists for requirements_for_test.txt installs
COPY --from=python_build --chown=notify:notify /home/vcap/kombu /home/vcap/kombu

# Copy the notifications-api repo contents
COPY --chown=notify:notify notifications-api/ .

ENV SQLALCHEMY_DATABASE_URI=postgresql+psycopg2://postgres:postgres@localhost:5432/
ENV UV_CACHE_DIR='/tmp/uv-cache/'
RUN uv pip sync requirements_for_test.txt


USER root

ENV POSTGRES_VERSION=15 \
    POSTGRES_REPO_KEY=B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8

RUN \
    apt-get update \
    && ap
