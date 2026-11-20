# rt-phantom-mcp-ops

Offline radiotherapy physics QA automation & hybrid-cloud research ops stack. Connects deterministic synthetic water-phantom Monte Carlo dose verification (`3D Gamma-index` + `DVH` checks), hybrid-cloud/NAS cold-backup integrity auditing, and a **Remote MCP** server designed for native **iOS App Intents / SwiftUI** monitoring and multi-agent **Devin Bots** workflows.

> **Clinical Safety Boundary:** This repository is strictly for **offline academic research and synthetic/water-phantom QA validation**. Zero patient health information (PHI), zero live clinical TPS hooks, and zero linear accelerator control interfaces exist in this codebase.

## Architecture & Persistent Bot Responsibilities

| Bot Role | Owned Responsibility | Target Modules |
| :--- | :--- | :--- |
| **Simulation & Pipeline Bot** | Maintain Python/C# Monte Carlo synthetic phantom benchmarks, PDD/profile tolerances, and on-demand CPU batch orchestration | `scripts/gamma_phantom_check.py`, `tests/` |
| **Infra & Backup Reliability Bot** | Monitor FRP relay tunnel health, local compute nodes, and NAS cold-backup SHA-256 manifest integrity | `mcp_server/server.py`, `docker-compose.yml` |
| **iOS & Remote MCP Companion Bot** | Maintain Remote MCP schema parity for the SwiftUI / App Intents client (DVH diff inspection, lock-screen burn monitoring, `Needs You` approvals) | `mcp_server/`, `ios/` (upcoming) |
| **Sandbox QA Bot** | Rebuild isolated Docker Compose test environments on every PR and enforce zero silent numerical regressions | `Dockerfile`, `tests/` |

## Quickstart

### 1. Run Synthetic Water-Phantom 3D Gamma & DVH Check
```bash
python3 scripts/gamma_phantom_check.py --dd 2.0 --dta 2.0 --out reports/latest_qa_report.json
```

### 2. Run Unit & Numerical Regression Tests
```bash
python3 -m unittest discover -s tests -v
```

### 3. Start the Remote MCP Server via Docker Compose
```bash
docker compose up --build
```

Verify the MCP endpoint locally:
```bash
curl -s http://localhost:8765/health
curl -s -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Roadmap
- [x] Synthetic 3D water-phantom PDD/dose grid generator & 3D Gamma-index evaluator (AAPM TG-218 style thresholds)
- [x] Stdlib JSON-RPC 2.0 Remote MCP server (`get_latest_gamma_report`, `verify_nas_cold_backup_checksum`, `get_frp_tunnel_status`)
- [x] Containerized sandbox runner (`Dockerfile` + `docker-compose.yml`)
- [ ] Full AAPM TG-119 multi-phantom DICOM-RT benchmark suite
- [ ] Native SwiftUI + App Intents iOS companion client for DVH diff review and `Needs You` Bot approvals
