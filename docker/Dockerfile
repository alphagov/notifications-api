FROM python:3.9-slim-bullseye as parent

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

WORKDIR /home/vcap/app

COPY requirements.txt ./

# RUN useradd celeryuser

RUN \
    echo "Installing python dependencies" \
    && pip install -r requirements.txt

COPY app app
COPY run_celery.py .
COPY environment.sh .
COPY Makefile .
