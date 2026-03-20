import logging
import os
import random
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ─── App ────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ─── Prometheus Metrics ──────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "app_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"]
)

REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
)

ERROR_COUNT = Counter(
    "app_errors_total",
    "Total number of application errors",
    ["endpoint", "error_type"]
)

ACTIVE_REQUESTS = Gauge(
    "app_active_requests",
    "Number of requests currently being processed"
)

APP_INFO = Gauge(
    "app_info",
    "Application metadata",
    ["version", "environment"]
)

APP_INFO.labels(
    version=os.getenv("APP_VERSION", "1.0.0"),
    environment=os.getenv("ENVIRONMENT", "development")
).set(1)

# ─── Middleware ───────────────────────────────────────────────────────────────
@app.before_request
def before_request():
    request.start_time = time.time()
    ACTIVE_REQUESTS.inc()

@app.after_request
def after_request(response):
    latency = time.time() - request.start_time
    endpoint = request.path
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(latency)
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=response.status_code
    ).inc()
    ACTIVE_REQUESTS.dec()
    return response

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return jsonify({
        "service": "auto-healing-demo",
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    })

@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

@app.route("/ready")
def ready():
    return jsonify({"status": "ready"}), 200

@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

@app.route("/work")
def work():
    duration = random.uniform(0.05, 0.3)
    time.sleep(duration)
    logger.info(f"Work done in {duration:.3f}s")
    return jsonify({
        "message": "Work completed",
        "duration_ms": round(duration * 1000, 2)
    })

@app.route("/chaos", methods=["GET", "POST"])
def chaos():
    mode = request.args.get("mode", "random")

    if mode == "latency":
        delay = random.uniform(2.0, 6.0)
        logger.warning(f"[CHAOS] Injecting latency: {delay:.2f}s")
        time.sleep(delay)
        return jsonify({"chaos": "latency", "delay_s": round(delay, 2)}), 200

    elif mode == "error":
        logger.error("[CHAOS] Injecting 500 error")
        ERROR_COUNT.labels(endpoint="/chaos", error_type="injected_500").inc()
        return jsonify({"chaos": "error", "message": "Injected failure"}), 500

    else:
        roll = random.random()
        if roll < 0.33:
            delay = random.uniform(2.0, 6.0)
            logger.warning(f"[CHAOS] Random → latency {delay:.2f}s")
            time.sleep(delay)
            return jsonify({"chaos": "latency", "delay_s": round(delay, 2)}), 200
        elif roll < 0.66:
            logger.error("[CHAOS] Random → 500 error")
            ERROR_COUNT.labels(endpoint="/chaos", error_type="random_500").inc()
            return jsonify({"chaos": "error"}), 500
        else:
            return jsonify({"chaos": "none", "message": "Lucky! No chaos this time."}), 200

@app.errorhandler(404)
def not_found(e):
    ERROR_COUNT.labels(endpoint="unknown", error_type="404").inc()
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    ERROR_COUNT.labels(endpoint="unknown", error_type="500").inc()
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Starting app on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
