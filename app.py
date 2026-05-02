from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

latest_data = {
    "temp_bme": 0.0,
    "humidity": 0.0,
    "pressure": 0.0,
    "temp_object": 0.0,
    "temp_ambient": 0.0,
    "timestamp": "No data yet"
}

@app.route("/")
def index():
    return open("index.html").read()

@app.route("/data", methods=["POST"])
def receive():
    global latest_data
    d = request.get_json()
    if d:
        latest_data = d
        latest_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Data: {latest_data}")
        return jsonify({"status":"ok"}), 200
    return jsonify({"status":"error"}), 400

@app.route("/api/data")
def send():
    return jsonify(latest_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
