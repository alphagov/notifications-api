echo "Install dependencies"
cd /home/ubuntu/notifications-api;
pip3 install -r /home/ubuntu/notifications-api/requirements.txt
python3 db.py db upgrade
