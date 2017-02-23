#!/bin/bash

set -eo pipefail

echo "Install dependencies"

cd /home/notify-app/notifications-api;
pip3 install --no-index --find-links=wheelhouse wheelhouse/*
