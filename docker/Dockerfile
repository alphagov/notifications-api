FROM python:3.9-slim-bullseye as parent

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libcurl4-openssl-dev \
    curl \
    libssl-dev \
    && apt-get -y clean \
    && rm -rf /var/lib/apt/lists/* /tmp/*

RUN groupadd -r notify && useradd -r -g notify notify

WORKDIR /home/vcap/app

COPY requirements.txt ./

RUN echo "Installing python dependencies" \
    && pip install -r requirements.txt

COPY app app
COPY migrations migrations
COPY run_celery.py gunicorn_config.py application.py entrypoint.sh ./

RUN chown -R notify:notify /home/vcap/app \
    && chmod +x /home/vcap/app/entrypoint.sh

USER notify

ENTRYPOINT [ "/home/vcap/app/entrypoint.sh" ]
