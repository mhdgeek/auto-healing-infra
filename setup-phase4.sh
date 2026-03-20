#!/bin/bash

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RESET='\033[0m'

step() { echo -e "\n  ${CYAN}▶ $1${RESET}"; }
ok()   { echo -e "  ${GREEN}✅ $1${RESET}"; }

echo ""
echo -e "  ${CYAN}🤖 Phase 4 — Auto-Healer Bot${RESET}"
echo ""

# ─── 1. Build healer image ────────────────────────────────────────────────────
step "Building auto-healer Docker image..."
docker build -t auto-healer:local ./healer
ok "Image built"

# ─── 2. Load into Kind ───────────────────────────────────────────────────────
step "Loading image into Kind cluster..."
kind load docker-image auto-healer:local --name auto-healing
ok "Image loaded"

# ─── 3. Apply RBAC ───────────────────────────────────────────────────────────
step "Applying RBAC (ServiceAccount + Role + RoleBinding)..."
kubectl apply -f k8s/healer-rbac.yml
ok "RBAC configured"

# ─── 4. Deploy healer ────────────────────────────────────────────────────────
step "Deploying auto-healer..."
kubectl apply -f k8s/healer-deployment.yml

echo "  Waiting for healer to be ready..."
kubectl rollout status deployment/auto-healer -n app --timeout=90s
ok "Auto-healer deployed"

# ─── 5. Verify ───────────────────────────────────────────────────────────────
step "Verifying pods..."
kubectl get pods -n app

# ─── 6. Test the healer webhook manually ─────────────────────────────────────
step "Testing healer webhook..."
kubectl port-forward svc/auto-healer 8000:8000 -n app &
PF_PID=$!
sleep 3

echo "  Sending test alert to healer..."
curl -s -X POST http://localhost:8000/alert \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "FlaskHighErrorRate",
        "namespace": "app",
        "severity": "critical"
      },
      "annotations": {
        "summary": "Test alert from setup script"
      }
    }]
  }' | python3 -m json.tool

echo ""
echo "  Checking incident log..."
curl -s http://localhost:8000/incidents | python3 -m json.tool

kill $PF_PID 2>/dev/null || true

# ─── 7. Done ─────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}✅ Phase 4 complete!${RESET}"
echo ""
echo -e "  ${YELLOW}Watch the healer logs:${RESET}"
echo "  kubectl logs -f deploy/auto-healer -n app"
echo ""
echo -e "  ${YELLOW}View incident history:${RESET}"
echo "  kubectl port-forward svc/auto-healer 8000:8000 -n app"
echo "  curl http://localhost:8000/incidents"
echo ""
echo -e "  ${YELLOW}Trigger a real alert:${RESET}"
echo "  kubectl port-forward svc/flask-app 5001:80 -n app &"
echo "  for i in \$(seq 1 20); do curl -s 'http://localhost:5001/chaos?mode=error' > /dev/null; done"
echo ""
