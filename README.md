# 🔧 Auto-Healing Infrastructure

![CI/CD](https://github.com/mhdgeek/auto-healing-infra/actions/workflows/ci-cd.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![Kubernetes](https://img.shields.io/badge/Kubernetes-1.34-326CE5?logo=kubernetes)
![Prometheus](https://img.shields.io/badge/Prometheus-monitoring-E6522C?logo=prometheus)
![Grafana](https://img.shields.io/badge/Grafana-dashboards-F46800?logo=grafana)

> A production-grade SRE project that automatically detects and remediates infrastructure incidents without human intervention.

## 🏗️ Architecture

```
Developer → GitHub → CI/CD Pipeline → Kubernetes Cluster
                                            │
                          ┌─────────────────┼─────────────────┐
                          │                 │                 │
                     Flask App         Prometheus        Auto-Healer
                     (3 replicas)      + Grafana         (webhook bot)
                          │                 │                 │
                          └────── metrics ──┘                 │
                                    │                         │
                               alert fires ──────────────────►│
                                                         rolling restart
```

## ⚡ Quick Start

```bash
git clone https://github.com/mhdgeek/auto-healing-infra.git
cd auto-healing-infra
make up
open http://localhost:3000   # Grafana
```

## 🔥 See Auto-Healing in Action

```bash
kubectl port-forward svc/auto-healer 8000:8000 -n app &
curl -X POST http://localhost:8000/alert \
  -H "Content-Type: application/json" \
  -d '{"alerts":[{"status":"firing","labels":{"alertname":"FlaskHighErrorRate","namespace":"app"}}]}'
kubectl get pods -n app -w
curl http://localhost:8000/incidents
```

## 📊 Alerting Rules

| Alert | Condition | Action |
|---|---|---|
| `FlaskHighErrorRate` | Error rate > 10% for 1m | Rolling restart |
| `FlaskHighLatency` | P99 latency > 2s for 1m | Rolling restart |
| `FlaskAppDown` | Replicas < 2 for 30s | Scale up |
| `FlaskPodCrashLooping` | Restarts > 3 in 15m | Delete crashlooping pods |

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| App | Python / Flask |
| Containers | Docker (multi-stage) |
| Orchestration | Kubernetes (Kind) |
| Monitoring | Prometheus + Grafana |
| Alerting | Alertmanager |
| Auto-Healing | Python + kubernetes API |
| CI/CD | GitHub Actions |
| Security | Trivy |

## 🚀 CI/CD Pipeline

```
push to main
    │
    ├── 1. Lint (ruff) + Tests (pytest)
    ├── 2. Build & Push Docker images → GHCR
    ├── 3. Security scan (Trivy)
    └── 4. Deploy to Kind + Smoke tests
```
