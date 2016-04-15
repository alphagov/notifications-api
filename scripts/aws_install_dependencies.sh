echo "Install dependencies"
cd /home/notify-app/notifications-api;
pip3 install -r /home/notify-app/notifications-api/requirements.txt
python3 db.py db upgrade
