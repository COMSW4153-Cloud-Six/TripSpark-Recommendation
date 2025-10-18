from flask import Flask
from flask_cors import CORS
import controllers

app = Flask(__name__)
CORS(app)

@app.route("/health", methods=["GET"])
def health():
    return controllers.health()

@app.route("/recommendations", methods=["POST"])
def create_recommendations():
    return controllers.create_recommendations()

@app.route("/recommendations/<recId>", methods=["GET", "PUT", "DELETE"])
def rec_operations(recId):
    return controllers.not_implemented(recId)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
