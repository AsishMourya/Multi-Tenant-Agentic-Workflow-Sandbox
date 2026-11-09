# Multi-Tenant Agentic Workflow Sandbox

A single-machine learning sandbox for synthetic Python and agent exercises. The
dashboard is a React app; the authenticated Python control plane provisions
disposable Firecracker environments, enforces tenant ownership and resource
policy, brokers approved mock-tool calls, and records deterministic plus optional
semantic grading evidence.

## Run the web demo

Run the app from WSL Ubuntu only. From the repository directory in WSL:

```bash
bash start-demo.sh
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080), copy the `tenant-a` token from
`config/tenants.local.json` into the dashboard, choose an exercise, and click
**Run**. The first launch installs the Python dependencies, builds the
React frontend, and creates the local-only demo credentials. The frontend and API
are served together; no separate Node server is required. See [RUNBOOK.md](RUNBOOK.md)
for the short demo walkthrough and troubleshooting.

## Exercises

- **Python - `orders-cents`:** aggregate order totals in integer cents.
- **Python - `daily-revenue`:** group daily revenue totals in integer cents.
- **Workflow - `inventory`:** check stock with one scoped mock lookup.
- **Workflow - `stock-reorder`:** calculate a reorder amount from the lookup.
- **Agent - `inventory-brief`:** produce a short evidence-backed availability brief.
- **Agent - `order-explainer`:** explain order cost alongside stock availability.

All six IDs have manifests, references, schemas, and deterministic contract checks.
All six dashboard starter examples completed live Firecracker runs with deterministic
checks passing on 2026-11-09; all four workflows restored VM snapshots. A ten-request
burst across two tenants also completed through the two-worker admission queue.
These are bounded local probes, not grading-quality or broad security validation.

The browser never chooses a tenant ID directly. It sends a bearer token; the
control plane derives the tenant, owns the tool capability, and records the
execution and grade. Only synthetic data and dummy credentials belong here.

## Requirements and limitations

Genuine learner-code execution requires WSL2/Linux with root access, working KVM
(API version 12), and the pinned Firecracker binary, kernel, and guest image under
`/root/dat-backend`. The launch command prints a host preflight. If those resources
are missing, the UI can start, but the platform reports execution as unavailable;
it never substitutes unrestricted host Python execution.

The app is intended for a local loopback demo, not public deployment. The
milestone evidence and remaining validation gaps are documented in
[PROJECT_STATUS.md](PROJECT_STATUS.md).
