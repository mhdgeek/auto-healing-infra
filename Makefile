.PHONY: help install test build up down logs chaos-latency chaos-error chaos-random status clean

CYAN  := \033[0;36m
GREEN := \033[0;32m
RESET := \033[0m

help:
	@echo ""
	@echo "  $(CYAN)Auto-Healing Infrastructure — Phase 1$(RESET)"
	@echo ""
	@echo "  $(GREEN)make install$(RESET)         Install Python deps locally"
	@echo "  $(GREEN)make test$(RESET)            Run all unit tests"
	@echo "  $(GREEN)make up$(RESET)              Start all services"
	@echo "  $(GREEN)make down$(RESET)            Stop all services"
	@echo "  $(GREEN)make logs$(RESET)            Follow app logs"
	@echo "  $(GREEN)make status$(RESET)          Show container status"
	@echo "  $(GREEN)make chaos-latency$(RESET)   Inject latency"
	@echo "  $(GREEN)make chaos-error$(RESET)     Inject 500 error"
	@echo "  $(GREEN)make chaos-random$(RESET)    5 random chaos requests"
	@echo "  $(GREEN)make clean$(RESET)           Remove everything"
	@echo ""

install:
	pip install -r app/requirements.txt pytest pytest-cov

test:
	pytest tests/ -v

build:
	docker build -t auto-healing-app:local ./app

up:
	docker compose up -d --build
	@echo ""
	@echo "  $(GREEN)✅ Services started:$(RESET)"
	@echo "  App        → http://localhost:5000"
	@echo "  Prometheus → http://localhost:9090"
	@echo "  Grafana    → http://localhost:3000  (admin/admin)"
	@echo ""

down:
	docker compose down

logs:
	docker compose logs -f app

status:
	docker compose ps

chaos-latency:
	@echo "$(CYAN)Injecting latency...$(RESET)"
	curl -s "http://localhost:5000/chaos?mode=latency" | python3 -m json.tool

chaos-error:
	@echo "$(CYAN)Injecting 500 error...$(RESET)"
	curl -s "http://localhost:5000/chaos?mode=error" | python3 -m json.tool

chaos-random:
	@echo "$(CYAN)Sending 5 random chaos requests...$(RESET)"
	@for i in 1 2 3 4 5; do \
		echo "  → Request $$i:"; \
		curl -s "http://localhost:5000/chaos?mode=random" | python3 -m json.tool; \
		sleep 1; \
	done

clean:
	docker compose down -v
	docker rmi auto-healing-app:local 2>/dev/null || true

# ─── Phase 2 : Kubernetes ────────────────────────────────────────────────────

cluster-create: ## Create Kind cluster (1 control-plane + 2 workers)
	kind create cluster --config k8s/cluster/kind-config.yaml
	kubectl cluster-info --context kind-auto-healing

cluster-delete: ## Delete the Kind cluster
	kind delete cluster --name auto-healing

k8s-load-image: ## Load local Docker image into Kind
	kind load docker-image auto-healing-app:local --name auto-healing

k8s-deploy: ## Deploy the app to Kubernetes
	kubectl apply -f k8s/app/namespace.yaml
	kubectl apply -f k8s/app/configmap.yaml
	kubectl apply -f k8s/app/deployment.yaml
	kubectl apply -f k8s/app/service.yaml
	kubectl apply -f k8s/app/hpa.yaml
	@echo ""
	@echo "  Waiting for pods to be ready..."
	kubectl wait --for=condition=ready pod -l app=flask-app -n app --timeout=60s
	@echo ""
	@echo "  ✅ App running → http://localhost:30000"

k8s-status: ## Show pods, services, hpa
	@echo "\n--- PODS ---"
	kubectl get pods -n app -o wide
	@echo "\n--- SERVICES ---"
	kubectl get svc -n app
	@echo "\n--- HPA ---"
	kubectl get hpa -n app

k8s-logs: ## Follow logs of all flask-app pods
	kubectl logs -f -l app=flask-app -n app --max-log-requests=10

k8s-chaos: ## Inject chaos into the cluster app
	curl -s "http://localhost:30000/chaos?mode=random" | python3 -m json.tool

k8s-kill-pod: ## Kill a random pod to test self-healing
	kubectl delete pod -n app $$(kubectl get pods -n app -l app=flask-app -o jsonpath='{.items[0].metadata.name}')
	@echo "  Pod deleted — watch K8s restart it automatically:"
	@echo "  kubectl get pods -n app -w"

k8s-watch: ## Watch pods in real time
	kubectl get pods -n app -w

# ─── Phase 3 : Observabilité K8s ─────────────────────────────────────────────

helm-add-repos: ## Add Prometheus & Grafana Helm repos
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update

monitoring-install: ## Install kube-prometheus-stack via Helm
	kubectl apply -f k8s/monitoring/namespace.yaml
	helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
		--namespace monitoring \
		--set grafana.adminPassword=admin \
		--set grafana.service.type=NodePort \
		--set grafana.service.nodePort=32000 \
		--set prometheus.service.type=NodePort \
		--set prometheus.service.nodePort=32090 \
		--set alertmanager.enabled=false \
		--set kubeEtcd.enabled=false \
		--set kubeScheduler.enabled=false \
		--set kubeControllerManager.enabled=false \
		--wait --timeout=5m
	@echo "  ✅ Prometheus → http://localhost:32090"
	@echo "  ✅ Grafana    → http://localhost:32000 (admin/admin)"

monitoring-apply: ## Apply ServiceMonitor and alert rules
	kubectl apply -f k8s/monitoring/servicemonitor.yaml
	kubectl apply -f k8s/monitoring/alert-rules.yaml
	kubectl apply -f k8s/monitoring/grafana-dashboard-configmap.yaml

monitoring-status: ## Check monitoring pods
	kubectl get pods -n monitoring

monitoring-forward-grafana: ## Port-forward Grafana to localhost:3000
	kubectl port-forward svc/prometheus-grafana -n monitoring 3000:80

monitoring-forward-prometheus: ## Port-forward Prometheus to localhost:9090
	kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090

chaos-load: ## Send 200 requests to generate traffic
	@echo "Generating traffic..."
	@for i in $$(seq 1 200); do \
		curl -s "http://localhost:30000/work" > /dev/null; \
		curl -s "http://localhost:30000/chaos?mode=random" > /dev/null; \
		sleep 0.2; \
	done
	@echo "Done!"
