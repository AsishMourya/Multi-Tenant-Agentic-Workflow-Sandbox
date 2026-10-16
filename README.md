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
`Platform.submit` path uses trusted reference fixtures. A separate isolated
submission path now stages learner code in per-session Firecracker disks and
uses safe points for full-VM restoration. The 15 October feasibility spike
booted and restored a VM; the new integrated path has only offline checks so
far because KVM stopped working in WSL on 16 October. See
`WEEK1-4_STATUS_2026-10-16.md` for dated evidence and remaining M1-M4 gaps.

## Start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v
.\.venv\Scripts\python.exe -m scripts.prototype --output evidence/prototype.json
```

## Firecracker integration path (Linux root)

The trusted fixture demo above does not execute learner source. The isolated
path uses `Platform.submit_code` or `Platform.submit_workflow_code` with
`FirecrackerBackend`; `TenantGateway` derives ownership from opaque bearer
credentials. It fails closed if KVM or the pinned guest image is unavailable.

From the repository root in WSL, after preparing the Firecracker binary, kernel,
and `ubuntu.ext4` under `/root/dat-backend`:

```bash
pip3 download --only-binary=:all: --platform manylinux2014_x86_64 \
  --python-version 3.12 --implementation cp --abi cp312 \
  -r requirements-lock.txt -d work/backend/wheels
python3 scripts/prepare_guest_image.py --output evidence/guest-image.json
python3 scripts/guest_chroot_probe.py --output evidence/guest-chroot.json
python3 scripts/python_chroot_probe.py --output evidence/python-chroot.json
python3 scripts/isolated_demo.py --output evidence/isolated-demo.json
python3 scripts/firecracker_resource_probe.py --output evidence/resource-probe.json
```

`prepare_guest_image.py` creates a new image and refuses to overwrite an existing
one. The chroot probe verifies the installed packages and broker handshake only.
The live demo requires working KVM; it runs one Python and one LangGraph
submission in separate VMs and restores both from full snapshots. The backend
checks each artifact against `config/firecracker_backend_lock.json`. The demo
uses fixture judge responses. Check the dated status report before claiming
M1-M4 completion.
