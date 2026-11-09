# Development Runbook

## Presentation demo (one command)

From the repository directory in WSL Ubuntu, run `bash start-demo.sh`. Keep that
terminal open and visit http://127.0.0.1:8080/ on the same machine. Copy the
`tenant-a` value from the local-only `config/tenants.local.json` into **Tenant
token**. Do not show the token file or terminal containing it on a shared screen.

1. Select **Order totals**, keep the prefilled code and JSON input, and click **Run**.
   The expected output is `apple: 250`, `pear: 80`, and `total_cents: 330`.
2. Select **Inventory check**, keep the prefilled example, and click **Run**.
   For two apples, the mock lookup returns seven available and `accepted: true`.
   Open **Execution details** to discuss the isolated backend and grade checks.
3. Optionally change an input or source and run again to show that a new tenant-owned
   session executes the submitted code, rather than displaying a fixed result.

The default launch does **not** configure the optional local semantic judge, so a
correct run normally shows **REVIEW** with deterministic checks passed and human
review pending. This is expected; it is not a VM or correctness failure. The
workflow takes longer because it captures and restores a full VM snapshot. Stop
the server with Ctrl+C after the presentation.

Most files in `scripts/` are development probes and evidence collectors, not
presentation steps. `start-demo.sh` (or the VS Code **Run DAT demo** task) is the only
launcher needed for the live UI;
`scripts/serve.py` is its API entry point. The remaining scripts cover historical
backend feasibility, resource/security probes, grading evaluation, and reproducible
evidence. They are useful for verification, but the audience need not run them.

## Scope

The platform registers six exercise IDs: two Python tasks and four inventory-backed
LangGraph tasks. It uses Firecracker on WSL/Linux for learner code. All six dashboard
starter examples passed live Firecracker execution and deterministic checks on
2026-11-09; the four workflows also restored full VM snapshots. See
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

The current suite is 85 tests. Windows skips five tests that require Linux root or
Linux file locks; the WSL root run executes all 85.

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

The local, Git-ignored `evidence/` files are bounded results, not universal security claims.
Current relevant probes include:

- `live-isolated-demo-2026-11-04.json`: two overlapping tenant runs, restoration, owner denial, cleanup.
- `live-api-workflow-probe-2026-11-09.json`: authenticated API workflow execution and snapshot restore.
- `live-firecracker-probe-2026-11-09.json`: Firecracker v1.17.0 snapshot artifacts and restore observations.
- `live-resource-probe-2026-11-09.json`: limits, network denials, and concurrent benign control.
- `live-security-probe-2026-11-09.json`: protected guest files, host-mount absence, broker bypass denial, canary absence.
- `local-judge-probe-2026-11-09.json`: two-call Qwen2.5 0.5B/Ollama JSON smoke test, not a quality evaluation.
- `live-all-exercises-2026-11-09.json`: all six dashboard starter examples completed in Firecracker with deterministic checks passing; workflows restored VM snapshots.
- `live-burst-ten-2026-11-09.json`: ten simultaneous API submissions across two synthetic tenants all completed, eight queued; server capacity was two workers, not ten concurrent VMs.

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

- The ten-request burst completed with two workers; sustained load and ten simultaneous
  VMs are not measured.
- Writable disk uses a fixed-size base image; a separate disk quota is not enforced.
- The installed Qwen2.5 0.5B judge sometimes returns invalid rubric judgments on real
  workflow evidence. These now yield **REVIEW**, not a trusted semantic score or an
  infrastructure retry. Human-label accuracy and calibration remain unmeasured.
- E2B Runtime/Embed has not been evaluated. The current backend is direct Firecracker;
  record why this remains selected or run the requested E2B feasibility comparison.
- The current `evaluation/labels.template.json` is intentionally empty. Collect real
  independent ratings and mentor approval; do not fabricate either.
