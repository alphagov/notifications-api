#!/bin/bash

echo "Chown application to be owned by ubuntu"
cd /home/ubuntu/;
chown -R ubuntu:ubuntu notifications-api
