from flask import jsonify
from .. import main


@main.route('/notification', methods=['POST'])
def create_notification():
    return jsonify(result="created"), 201
