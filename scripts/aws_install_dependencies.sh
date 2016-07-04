echo "Install dependencies"


if [ -e "/home/notify-app" ]
then
 	echo "Depenencies for notify-app"
	cd /home/ubuntu/notifications-api;
	pip3 install -r /home/notify-app/notifications-api/requirements.txt
	python3 db.py db upgrade
fi
else
 	echo "Depenencies for ubuntu"
	cd /home/ubuntu/notifications-api;
	pip3 install -r /home/ubuntu/notifications-api/requirements.txt
	python3 db.py db upgrade
fi