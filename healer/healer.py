import json
import logging
import os
import time
from datetime import datetime, timezone
from threading import Lock

from flask import Flask, jsonify, request
from kubernetes import client, config

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ─── App ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ─── In-memory incident log ──────────────────────────────────────────────────
incidents = []
incidents_lock = Lock()

# ─── Anti-flapping: track last heal time per alert ───────────────────────────
last_healed = {}
COOLDOWN_SECONDS = 120   # Don't heal same alert twice within 2 minutes

# ─── Load K8s config ─────────────────────────────────────────────────────────
def load_k8s():
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster K8s config")
    except Exception:
        config.load_kube_config()
        logger.info("Loaded local kube config")

load_k8s()

# ─── Slack notification ──────────────────────────────────────────────────────
def notify_slack(message: str, color: str = "good"):
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.info(f"[SLACK] {message}")
        return

    import urllib.request
    payload = json.dumps({
        "attachments": [{
            "color": color,
            "text": message,
            "footer": "auto-healer",
            "ts": int(time.time())
        }]
    }).encode()

    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning(f"Slack notification failed: {e}")

# ─── Healing strategies ───────────────────────────────────────────────────────
def rolling_restart(namespace: str, deployment: str) -> str:
    """Patch deployment to trigger a rolling restart."""
    apps_v1 = client.AppsV1Api()
    now = datetime.now(timezone.utc).isoformat()
    patch = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "auto-healer/restart-time": now
                    }
                }
            }
        }
    }
    apps_v1.patch_namespaced_deployment(deployment, namespace, patch)
    return f"Rolling restart triggered on {namespace}/{deployment}"


def scale_up(namespace: str, deployment: str, replicas: int = 4) -> str:
    """Scale up deployment replicas."""
    apps_v1 = client.AppsV1Api()
    patch = {"spec": {"replicas": replicas}}
    apps_v1.patch_namespaced_deployment(deployment, namespace, patch)
    return f"Scaled {namespace}/{deployment} to {replicas} replicas"


def delete_crashlooping_pods(namespace: str) -> str:
    """Delete pods in CrashLoopBackOff state."""
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace)
    deleted = []
    for pod in pods.items:
        for cs in (pod.status.container_statuses or []):
            if cs.state.waiting and cs.state.waiting.reason == "CrashLoopBackOff":
                v1.delete_namespaced_pod(pod.metadata.name, namespace)
                deleted.append(pod.metadata.name)
    if deleted:
        return f"Deleted crashlooping pods: {', '.join(deleted)}"
    return "No crashlooping pods found"


# ─── Decision engine ──────────────────────────────────────────────────────────
HEALING_STRATEGIES = {
    "FlaskHighLatency":    lambda ns, dep: rolling_restart(ns, dep),
    "FlaskHighErrorRate":  lambda ns, dep: rolling_restart(ns, dep),
    "FlaskAppDown":        lambda ns, dep: scale_up(ns, dep),
    "FlaskPodCrashLooping": lambda ns, dep: delete_crashlooping_pods(ns),
}

def heal(alert_name: str, namespace: str, deployment: str) -> dict:
    """Apply the right healing strategy for the given alert."""

    # Anti-flapping check
    key = f"{alert_name}:{namespace}/{deployment}"
    now = time.time()
    if key in last_healed:
        elapsed = now - last_healed[key]
        if elapsed < COOLDOWN_SECONDS:
            msg = f"Skipping {alert_name} — cooldown ({int(COOLDOWN_SECONDS - elapsed)}s left)"
            logger.info(msg)
            return {"action": "skipped", "reason": msg}

    strategy = HEALING_STRATEGIES.get(alert_name)
    if not strategy:
        msg = f"No strategy for alert: {alert_name}"
        logger.warning(msg)
        return {"action": "unknown", "reason": msg}

    try:
        result = strategy(namespace, deployment)
        last_healed[key] = now
        logger.info(f"✅ Healed [{alert_name}]: {result}")
        return {"action": "healed", "result": result}
    except Exception as e:
        logger.error(f"❌ Healing failed [{alert_name}]: {e}")
        return {"action": "failed", "error": str(e)}


# ─── Webhook endpoint ─────────────────────────────────────────────────────────
@app.route("/alert", methods=["POST"])
def handle_alert():
    """Receives Alertmanager webhook and triggers healing."""
    data = request.get_json(force=True)
    logger.info(f"Received webhook: {json.dumps(data, indent=2)}")

    results = []

    for alert in data.get("alerts", []):
        alert_name = alert.get("labels", {}).get("alertname", "unknown")
        status     = alert.get("status", "unknown")       # firing | resolved
        namespace  = alert.get("labels", {}).get("namespace", "app")
        deployment = "flask-app"

        incident = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert": alert_name,
            "status": status,
            "namespace": namespace,
            "deployment": deployment,
            "action": None,
            "result": None,
        }

        if status == "firing":
            logger.warning(f"🔥 ALERT FIRING: {alert_name} in {namespace}")
            notify_slack(
                f"🔥 *ALERT*: `{alert_name}` firing in `{namespace}`\nTriggering auto-heal...",
                color="danger"
            )

            heal_result = heal(alert_name, namespace, deployment)
            incident["action"] = heal_result.get("action")
            incident["result"] = heal_result.get("result") or heal_result.get("reason")

            if heal_result["action"] == "healed":
                notify_slack(
                    f"✅ *AUTO-HEALED*: `{alert_name}`\n{heal_result['result']}",
                    color="good"
                )

        elif status == "resolved":
            logger.info(f"✅ ALERT RESOLVED: {alert_name}")
            notify_slack(
                f"✅ *RESOLVED*: `{alert_name}` in `{namespace}`",
                color="good"
            )
            incident["action"] = "resolved"

        with incidents_lock:
            incidents.append(incident)
            # Keep only last 100 incidents
            if len(incidents) > 100:
                incidents.pop(0)

        results.append(incident)

    return jsonify({"processed": len(results), "results": results}), 200


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


@app.route("/incidents")
def get_incidents():
    """Returns the incident history."""
    with incidents_lock:
        return jsonify({
            "total": len(incidents),
            "incidents": list(reversed(incidents))  # Most recent first
        })


@app.route("/incidents/clear", methods=["POST"])
def clear_incidents():
    with incidents_lock:
        incidents.clear()
    return jsonify({"message": "Incidents cleared"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Auto-healer starting on port {port}")
    app.run(host="0.0.0.0", port=port)
