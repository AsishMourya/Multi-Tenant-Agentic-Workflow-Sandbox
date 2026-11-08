# Development Runbook

## Scope

The platform registers six exercise IDs: two Python tasks and four inventory-backed
LangGraph tasks. It uses Firecracker on WSL/Linux for learner code. Live Firecracker
evidence currently covers `orders-cents` and `inventory`; the other four have contract
and mocked-controller integration tests but need live guest demonstrations. See
`PROJECT_STATUS.md` for current M1-M8 evidence and open acceptance work.

## Start the WSL Demo

Use Ubuntu 22.04 WSL with root access, working `/dev/kvm` (API version 12), and the
pinned Firecracker binary, kernel, and guest image under `/root/dat-backend`.
From the repository root inside WSL:

```bash
bash start-demo.sh
```

Open `http://127.0.0.1:8080/`. The demo creates a local credential file for two
synthetic tenants. Keep that file private; it is ignored by Git. Paste a tenant token
into the dashboard, choose an exercise, and run it. The API fails closed
if Firecracker/KVM artifacts are unavailable; it does not fall back to host execution.
Stop the service with Ctrl+C.

## Tests

Windows contract suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v
```

WSL root suite, including guest process/resource limits and Linux resume locks:

```bash
cd /mnt/c/Users/asish/OneDrive/Documents/College/7/DAT
sudo -H .venv-linux/bin/python -m unittest discover -s tests -p 'test*.py' -v
```

The current suite is 78 tests. Windows skips five tests that require Linux root or
Linux file locks; the WSL root run executes all 78.

Build the static dashboard and audit npm dependencies:

```bash
npm --prefix web ci
npm --prefix web run build
npm --prefix web audit
```

The current WSL default Node is 12.22.9. Vite 2 builds there but has development-tool
advisories; upgrading Vite requires upgrading the WSL Node runtime first. Production
npm dependencies currently report no advisories.

## Live Evidence

The checked-in `evidence/` files are bounded results, not universal security claims.
Current relevant probes include:

- `live-isolated-demo-2026-11-04.json`: two overlapping tenant runs, restoration, owner denial, cleanup.
- `live-api-workflow-probe-2026-11-09.json`: authenticated API workflow execution and snapshot restore.
- `live-firecracker-probe-2026-11-09.json`: Firecracker v1.17.0 snapshot artifacts and restore observations.
- `live-resource-probe-2026-11-09.json`: limits, network denials, and concurrent benign control.
- `live-security-probe-2026-11-09.json`: protected guest files, host-mount absence, broker bypass denial, canary absence.
- `local-judge-probe-2026-11-09.json`: two-call Qwen2.5 0.5B/Ollama JSON smoke test, not a quality evaluation.

Re-run live probes only from WSL with the prepared root backend and local-only test
fixtures. Do not run these probes against real external services or real credentials.

## Evaluation Data

The six-exercise/60-submission evaluation set and human labels are still pending. Do
not use generated examples as human ratings. Start from
`evaluation/submissions.template.json`; each real row needs a unique `id`, a `family`,
and an `exercise_id`:

```json
{
  "submissions": [
    {"id": "opaque-001", "family": "variant-family-01", "exercise_id": "orders-cents"}
  ]
}
```

Prepare the split before collecting or viewing labels:

```bash
.venv-linux/bin/python scripts/prepare_evaluation.py \
  --input evaluation/submissions.json \
  --output evaluation/split-assignments.json \
  --seed dat-eval-family-v1
```

The tool requires exactly 60 submissions across six exercises and finds a family-safe
20/40 calibration/held-out split. It fails if family sizes cannot make exactly 20
calibration rows. It writes only IDs, family IDs, exercise IDs, and split names; it does
not inspect, generate, or overwrite human labels. Preserve both raters' original files
and store adjudication separately. The metrics tool is:

```bash
.venv-linux/bin/python scripts/evaluate_labels.py \
  --labels evaluation/labels.json \
  --output evidence/grading-metrics.json
```

## Current Limitations

- Only `orders-cents` and `inventory` have live Firecracker demo evidence. Four new
  exercise IDs are registered and tested with mocked execution, but require guest runs.
- Live concurrency evidence is two overlapping tenants; the SRS burst-of-ten result
  is still missing.
- Writable disk uses a fixed-size base image; a separate disk quota is not enforced.
- Judge inference has a JSON smoke test, not human-label accuracy or calibration.
- E2B Runtime/Embed has not been evaluated. The current backend is direct Firecracker;
  record why this remains selected or run the requested E2B feasibility comparison.
- The current `evaluation/labels.template.json` is intentionally empty. Collect real
  independent ratings and mentor approval; do not fabricate either.
