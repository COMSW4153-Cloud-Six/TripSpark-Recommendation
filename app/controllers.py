#This is to handle API endpoints

from flask import jsonify, request
from recommender import get_recommendations

def health():
    return jsonify({"status": "OK"}), 200

def create_recommendations():
    try:
        user_input = request.get_json()
        result = get_recommendations(user_input)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def not_implemented(recId):
    return jsonify({"message": "NOT IMPLEMENTED"}), 501

