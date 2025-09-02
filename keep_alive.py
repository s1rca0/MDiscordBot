# keep_alive.py
from flask import Flask, jsonify
import threading
import os

app = Flask(__name__)

@app.route("/")
def home():
    # Simple text so uptime monitors can do a keyword check
    return "Morpheus is alive."

@app.route("/health")
def health():
    # Machine-readable health for dashboards / slash command pings
    return jsonify({
        "status": "ok",
        "service": "morpheus",
        "version": os.getenv("GIT_REV", "local"),
    }), 200

def _run():
    port = int(os.environ.get("PORT", 8080))
    # 0.0.0.0 is required on Replit/Railway
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()