# Secure Multi-Tenant Agentic Workflow Sandbox

A one-machine prototype for two synthetic tenants running two bounded learning
exercises through one small platform:

- `orders-cents`: standalone Python order aggregation;
- `inventory`: LangGraph workflow using one scoped local inventory mock.

The project-owned layer handles tenant ownership, lifecycle, broker permissions,
checkpoint policy, deterministic grading, semantic review records, and testable
security contracts. Execution plumbing should be reused from one selected backend,
with E2B Runtime/Embed evaluated first on Linux/KVM and OpenSandbox plus Docker/gVisor
as the fallback.

## Current Status

The local CLI/API flow, scoped broker, review records, five attack-contract cases,
and `inventory-safe-point-1` checkpoint survive the contract tests. The
current Windows/WSL code uses trusted reference fixtures; it is not yet an
arbitrary-code sandbox. Backend integration, resource enforcement, authenticated
API transport, queueing, cleanup, and real judge calibration remain next.

## Start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v
.\.venv\Scripts\python.exe -m scripts.prototype --output evidence/prototype.json
```
