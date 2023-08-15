FROM python:3.9-slim-bullseye as base

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    libcurl4 && \
    apt-get -y clean && \
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
    curl \
    libssl-dev && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*

COPY requirements.txt .

RUN echo "Installing python requirements" && \
    python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install -r requirements.txt

COPY . .
RUN make generate-version-file  # This file gets copied across

##### Production Image #######################################################
FROM base AS production

RUN groupadd -r notify && useradd -r -g notify notify && chown -R notify:notify /home/vcap
USER notify

RUN mkdir /home/vcap/logs

COPY --from=python_build --chown=root:root /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY --chown=notify:notify app app
COPY --chown=notify:notify migrations migrations
COPY --chown=notify:notify run_celery.py gunicorn_config.py application.py entrypoint.sh ./
COPY --from=python_build --chown=notify:notify /home/vcap/app/app/version.py app/version.py

RUN chown -R notify:notify /home/vcap/app && \
    chmod +x /home/vcap/app/entrypoint.sh

ENTRYPOINT [ "/home/vcap/app/entrypoint.sh" ]

##### Test Image ##############################################################
FROM production as test

USER root
RUN chown -R notify:notify /opt/venv
RUN echo "Install OS dependencies for test build" && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
			make \
      curl \
			git && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*
USER notify

# Make sure the app/ directory is there so that "make bootstrap" can create app/version.py
RUN mkdir -p app

# Install dev/test requirements
COPY --chown=notify:notify Makefile requirements.txt requirements_for_test.txt ./
RUN make bootstrap

COPY --chown=notify:notify . .
