# Secure Multi-Tenant Agentic Workflow Sandbox

A one-machine, Firecracker-backed platform for credential-authenticated synthetic
tenants running bounded Python and LangGraph agent exercises:

- `orders-cents`: standalone Python order aggregation;
- `inventory`: LangGraph agent using one scoped local `inventory.lookup` mock.

Learner code runs in disposable Firecracker guest disks. The platform controls
tenant ownership, admission, resource policy, snapshots, tool permissions, and
hybrid grading. Agent code receives neither platform credentials nor general
network access: the inventory mock is available only through the scoped broker.

## Features

- Credential-derived, multi-tenant session ownership.
- Disposable Firecracker environments for Python and LangGraph agent submissions.
- Bounded CPU, memory, process, output, file-size, and wall-clock execution.
- Deny-by-default guest networking with a scoped mock-tool broker.
- Full VM snapshot/restore at supported safe points.
- Fair admission queue, lifecycle cleanup, expiry handling, and tenant worker caps.
- Deterministic hidden-case and agent-tool-trace grading.
- Rubric-based local-judge adapter with human-review records.
- Authenticated JSON API and a lightweight browser dashboard.

## Architecture

```text
Browser / API client
        | bearer credential
        v
TenantGateway -> Platform -> Admission + Lifecycle + Grading
                           |
                           v
                    Firecracker guest
                           | scoped tool request
                           v
                      Broker / mock API
```

The browser never selects a tenant identity directly. The guest does not receive
platform credentials, and it cannot make general outbound network calls. Agent tool
requests are checked against the authenticated tenant, session, exercise,
capability, operation, arguments, expiry, and request ID.

## Start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v
.\.venv\Scripts\python.exe -m scripts.prototype --output evidence/prototype.json
```

## Firecracker integration path (Linux root)

The trusted fixture demo above does not execute learner source. The isolated path
uses `Platform.submit_code` or `Platform.submit_workflow_code` with
`FirecrackerBackend`; `TenantGateway` derives ownership from opaque bearer
credentials. It fails closed if KVM or the pinned guest image is unavailable.

From the repository root in WSL, after preparing the Firecracker binary, kernel,
and `ubuntu.ext4` under `/root/dat-backend`:

```bash
pip3 install -r requirements-lock.txt
python3 scripts/guest_chroot_probe.py --root /root/dat-backend --output evidence/guest-chroot.json
python3 scripts/python_chroot_probe.py --root /root/dat-backend --output evidence/python-chroot.json
python3 scripts/isolated_demo.py --root /root/dat-backend --output evidence/isolated-demo.json
python3 scripts/firecracker_resource_probe.py --root /root/dat-backend --output evidence/resource-probe.json
```

To use a local semantic judge, install an Ollama model locally and add, for example,
`--judge-model qwen2.5:0.5b` to the server command. For held-out grading evaluation,
copy `evaluation/labels.template.json`, retain both independent human ratings, then run:

```bash
python3 scripts/evaluate_labels.py --labels evaluation/labels.json --output evidence/label-metrics.json
```

Run the server with a clean root Python environment, because normal user-site
packages can override the pinned dependencies and root access is required for KVM:

```bash
sudo -H env PYTHONNOUSERSITE=1 python3 scripts/serve.py \
  --credentials config/tenants.local.json \
  --state-root work/platform-api \
  --backend-root /root/dat-backend
```

The chroot probes verify guest package and protocol readiness. The live demo runs
one Python and one LangGraph agent submission concurrently and restores both from
full snapshots. The resource probe exercises enforced limits and deny-by-default
guest networking.

## Local API and dashboard

`sandbox.api.SandboxService` exposes authenticated create, submit, status, and
delete operations. It ignores tenant fields and client-supplied judge data in JSON
payloads; ownership is derived exclusively from the bearer credential. The bundled
dashboard is served at `/` by the same stdlib HTTP handler and calls only those API
endpoints.

Create your own tenant credentials by copying the example to an ignored local file
and replacing every value with a unique random token of at least 32 characters.
The sample values are deliberately invalid placeholders and must not be used:

```bash
cp config/tenants.example.json config/tenants.local.json
sudo -H env PYTHONNOUSERSITE=1 python3 scripts/serve.py \
  --credentials config/tenants.local.json \
  --state-root work/platform-api \
  --backend-root /root/dat-backend
```

In PowerShell, use:

```powershell
Copy-Item config/tenants.example.json config/tenants.local.json
```

Open `http://127.0.0.1:8080/`, paste one tenant's bearer token, choose an exercise,
create a session, then submit source and JSON input. Add as many tenant name/token
pairs as needed to `tenants.local.json`; the API derives ownership from the token.
Run this command in WSL as root with KVM available for actual learner-code execution.

## Security model

Only synthetic exercises, mock APIs, and dummy secrets belong in this project.
The platform does not place long-lived upstream credentials in guest files,
environment variables, prompts, or logs. Deterministic grading and security policy
checks run outside the learner guest; model judgments cannot override a failed
invariant, policy violation, or infrastructure error.
