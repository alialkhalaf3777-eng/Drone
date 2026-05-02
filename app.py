import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

latest_data = {"temp_bme":0.0,"humidity":0.0,"pressure":0.0,"temp_object":0.0,"temp_ambient":0.0,"timestamp":"No data yet"}

HTML = open("index.html").read() if os.path.exists("index.html") else "<h1>Loading...</h1>"

@app.route("/")
def index():
    return HTML

@app.route("/data", methods=["POST"])
def receive():
    global latest_data
    d = request.get_json()
    if d:
        latest_data = d
        latest_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return jsonify({"status":"ok"}), 200
    return jsonify({"status":"error"}), 400

@app.route("/api/data")
def send():
    return jsonify(latest_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
