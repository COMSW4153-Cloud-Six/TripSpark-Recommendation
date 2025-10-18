#This is to handle API endpoints

from flask import jsonify, request
from recommender import get_recommendations

def health():
    return jsonify({"status": "OK"}), 200

def create_recommendations():
    user_input = request.get_json()
    result = get_recommendations(user_input)
    return jsonify(result), 200

def not_implemented(recId):
    return jsonify({"message": "NOT IMPLEMENTED"}), 501
