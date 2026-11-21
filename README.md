# Multi-Tenant Agentic Workflow Sandbox

A single-machine learning sandbox for synthetic Python and agent exercises. The
dashboard is a React app; the authenticated Python control plane provisions
disposable Firecracker environments, enforces tenant ownership and resource
policy, brokers approved mock-tool calls, and records deterministic plus optional
semantic grading evidence.

Project V, Group 44 (CS5903). Current status: the local prototype passes defined
VM, snapshot, resource, security, and deterministic tests. A real local model
produces provisional rubric judgments, but **human-labelled grading accuracy has
not been measured**. The final report is [Project_Report.pdf](docs/Project_Report.pdf)
and the material choices are in [Architecture_Decision_Records.md](docs/Architecture_Decision_Records.md).

The editable [report source](docs/Project_Report.md) can be rendered with
`python -m pip install reportlab==5.0.1` followed by
`python scripts/build_project_report.py` in a separate documentation environment.


Run the app from WSL Ubuntu only. From the repository directory in WSL:

```bash
bash start-demo.sh
```

For provisional real-model grading, start local Ollama with `qwen2.5:0.5b`
installed and run `bash start-demo.sh --with-judge`. Uncalibrated model decisions
remain pending human review even when a provisional score is available.
Explicit grading instructions found in learner output are routed directly to
review without a model score; this is a limited guard, not a complete defense.

Prerequisites: Ubuntu 22.04 under WSL2 (or a compatible Linux KVM host), root or
sudo, writable `/dev/kvm`, Python 3, Node/npm, and the pinned Firecracker v1.17.0
binary, kernel, and guest image under `/root/dat-backend`. The expected names and
SHA-256 values are in [firecracker_backend_lock.json](config/firecracker_backend_lock.json).
The VM artifacts are **not** in Git. Provision them and verify their hashes before
claiming a clean-clone live VM reproduction; [feasibility.py](scripts/feasibility.py)
checks the host and prints the missing pieces. The first online launch installs
dependencies from [requirements-lock.txt](requirements-lock.txt) and
[package-lock.json](web/package-lock.json); later `bash start-demo.sh --offline`
uses the installed copies. A failed KVM/backend preflight never falls back to
unrestricted host execution.

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
checks passing again on 2026-11-20; all four workflows restored VM snapshots. A
ten-request burst across two tenants completed through the two-worker admission
queue. The live resource probe passed the aggregate 32 MiB writable-scratch check,
and a 15-case bounded security corpus passed. These are local probes, not a claim
of grading accuracy or universal security.

The browser never chooses a tenant ID directly. It sends a bearer token; the
control plane derives the tenant, owns the tool capability, and records the
execution and grade. Only synthetic data and dummy credentials belong here.

The request path is dashboard -> authenticated API/tenant gateway -> bounded
admission -> disposable Firecracker guest. Workflow tool calls cross a scoped
host broker, and supported pause/resume uses a full same-host VM snapshot plus
artifact and policy checks. Guest output and tool traces feed deterministic
invariants, then an optional local judge, then a persisted grade/review queue.
The guest has no direct network access. See the architecture figure in the report
and [ADR-001 to ADR-006](docs/Architecture_Decision_Records.md).

For the prefilled order example, the expected JSON output has `apple: 250`,
`pear: 80`, and `total_cents: 330`. Four workflow starters also demonstrate
snapshot restoration. The complete screen-by-screen sequence is in
[RUNBOOK.md](RUNBOOK.md). Do not display the local tenant token file on a shared
screen. Stop the service with Ctrl+C; it listens only on `127.0.0.1:8080`.

## Tests and evaluation

Run the entire Linux/root contract suite from the checkout with
`sudo -H env PYTHONNOUSERSITE=1 .venv-linux/bin/python -m unittest discover -s tests -q`.
The latest recorded result was 125 passing tests in
[final-tests-2026-11-21.json](evidence/final-tests-2026-11-21.json).
Windows runs the same suite in `.venv` but skips five Linux-specific tests.
Build the static dashboard with `npm --prefix web ci` and
`npm --prefix web run build`. There is no separate database migration: the local
SQLite state is initialized by the control plane in ignored `work/`.

The [engineering bank](evaluation/regression-bank.json) and
[frozen split](evaluation/regression-split.json) provide 60 synthetic cases. The
[no-judge summary](evidence/regression-summary-2026-11-21.json) and
[judge-enabled summary](evidence/regression-judge-summary-2026-11-21.json)
are a same-workload engineering comparison, not accuracy against humans. The
separate [validation candidate bank](evaluation/validation-bank.json) has
partly-correct, ambiguous, and adversarial variants; its
[summary](evidence/validation-summary-2026-11-21.json) records 60 live runs and
model usage. The [15-case corpus](evidence/security-corpus-2026-11-20.json),
[three-round 1/2/4 benchmark](evidence/benchmark-concurrency-2026-11-21.json),
and raw JSONL files are retained in [evidence/](evidence/). The two independent
rating packets are **blank**; grading agreement, MAE, and pass/fail accuracy
must not be inferred from these engineering runs. Exact replay and adjudication
commands are in [RUNBOOK.md](RUNBOOK.md).

## Handover limits

The application is a loopback-only college prototype, not a public deployment.
Snapshots are same-host/pinned-runtime. Synthetic probes do not establish
universal isolation or prompt-injection resistance. A local judge has no API
fee but uses local memory/compute; Ollama and `qwen2.5:0.5b` are optional and
must be installed separately. Local credentials are generated in ignored
`config/tenants.local.json`; never commit them or real learner data. Known gaps,
including human ratings, mentor approval, contribution evidence, and final
submission tag, are itemized in the [report](docs/Project_Report.pdf).

The milestone evidence and remaining validation gaps are in the
[report source](docs/Project_Report.md); older development notes are not the
submission status of record.
