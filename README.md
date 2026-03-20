# 🔧 Auto-Healing Infrastructure — Phase 1

> Flask app with Prometheus metrics, chaos endpoints, and full Docker stack.

## Quick Start

```bash
make up                          # Start everything
curl http://localhost:5000/health
make chaos-error                 # Inject a failure
open http://localhost:3000       # Grafana (admin/admin)
open http://localhost:9090       # Prometheus
```

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | App info |
| `GET /health` | Liveness probe |
| `GET /ready` | Readiness probe |
| `GET /metrics` | Prometheus metrics |
| `GET /work` | Normal workload simulation |
| `GET /chaos?mode=latency` | Inject 2–6s latency |
| `GET /chaos?mode=error` | Return HTTP 500 |
| `GET /chaos?mode=random` | Random chaos |

## Tests

```bash
make install
make test
```

## Structure

```
auto-healing-infra/
├── app/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── tests/
│   └── test_app.py
├── monitoring/
│   ├── prometheus.yml
│   ├── alert-rules.yml
│   └── grafana-datasource.yml
├── docker-compose.yml
└── Makefile
```
