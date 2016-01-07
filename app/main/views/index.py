from flask import jsonify
from .. import main


# TODO need for health check url


# TODO remove
@main.route('/', methods=['GET'])
def get_index():
    return jsonify(result="hello world"), 200


# TODO remove
@main.route('/', methods=['POST'])
def post_index():
    return jsonify(result="hello world"), 200
