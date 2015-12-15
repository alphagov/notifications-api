from flask import jsonify
from .. import main


@main.route('/', methods=['GET'])
def get_index():
    return jsonify(result="hello world"), 200
