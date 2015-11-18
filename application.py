from flask import Flask

app = Flask(__name__)


@app.route('/')
def index():
    return 'Hello from notify-notifications-api'

if __name__ == '__main__':
    app.run(port=6011)
