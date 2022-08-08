FROM python:3.9-slim-bullseye as build

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

RUN echo "Install base packages" && apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && echo "Install binary app dependencies" \
    && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev \
    libssl-dev \
    && apt-get -y clean \
    && rm -rf /var/lib/apt/lists/* /tmp/*

RUN pip install --upgrade pip
RUN groupadd -r notify && useradd -r -g notify notify

WORKDIR /home/vcap/app

COPY requirements.txt ./

RUN echo "Installing python dependencies" \
    && pip install -r requirements.txt

COPY app app
COPY migrations migrations
COPY run_celery.py application.py gunicorn_config.py ./

USER notify

