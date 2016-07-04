#!/bin/bash


if [ -e "/home/notify-app" ]
then
 	echo "Chown application to be owned by notify-app"
	cd /home/notify-app/;
	chown -R notify-app:govuk-notify-applications notifications-api
else
	echo "Chown application to be owned by ubuntu"
	cd /home/ubuntu/;
	chown -R ubuntu:ubuntu notifications-api
fi