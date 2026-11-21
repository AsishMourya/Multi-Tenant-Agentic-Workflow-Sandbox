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
3. Select **Stock reorder** and click **Run**. The expected result is seven apples
   available and `reorder_quantity: 3`. In **Execution details**, point to
   `backend: firecracker`, the restored VM snapshot, and the deterministic checks.
4. Optionally change an input or source and run again to show that a new tenant-owned
   session executes the submitted code, rather than displaying a fixed result.

For an evidence slide, show the `checks` in `evidence/live-resource-probe-2026-11-20.json`
(including `aggregate_disk_limit`), the 15 PASS cases in
`evidence/security-corpus-2026-11-20.json`, and the summary of
`evidence/regression-runs-2026-11-20.jsonl` (60 synthetic runs: 12 REVIEW,
48 FAIL_INVARIANT, no infrastructure errors). Selected sanitized evidence is
available for handover in the repository; other probe outputs remain local and ignored;
do not imply they are human-rated accuracy results. The earlier ten-request burst
completed through a two-worker queue, not ten concurrent VMs.

The default launch does **not** configure the optional local semantic judge, so a
correct run normally shows **REVIEW** with deterministic checks passed and human
review pending. This is expected; it is not a VM or correctness failure. The
workflow takes longer because it captures and restores a full VM snapshot. Stop
the server with Ctrl+C after the presentation.

For a real local-model grading demo, start Ollama with `qwen2.5:0.5b` installed,
then run `bash start-demo.sh --with-judge` (combine with `--offline` if dependencies
are installed). The model runs twice after deterministic checks; its provisional
score, evidence, timings, and review reason are recorded. Until independent human
labels validate it, model-derived PASS/FAIL decisions remain **REVIEW** and require
a recorded human decision. Schema-valid output alone does not establish accuracy.
On the trusted host, `scripts/review_queue.py --summary` lists pending grade IDs
without dumping raw submissions. After a real reviewer inspects a grade's evidence,
record their decision with `scripts/review_queue.py --grade-id ID --reviewer NAME
--decision PASS|FAIL|ESCALATE --reason "reason"`; the review history is persisted.
This host-only command is not available to learner code.

Most files in `scripts/` are development probes and evidence collectors, not
presentation steps. `start-demo.sh` (or the VS Code **Run DAT demo** task) is the only
launcher needed for the live UI;
`scripts/serve.py` is its API entry point. The remaining scripts cover historical
backend feasibility, resource/security probes, grading evaluation, and reproducible
evidence. They are useful for verification, but the audience need not run them.

## Scope

The platform registers six exercise IDs: two Python tasks and four inventory-backed
LangGraph tasks. It uses Firecracker on WSL/Linux for learner code. All six dashboard
starter examples passed live Firecracker execution and deterministic checks again on
2026-11-20; the four workflows also restored full VM snapshots. See
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
cd /path/to/your/checkout
sudo -H env PYTHONNOUSERSITE=1 .venv-linux/bin/python -m unittest discover -s tests -p 'test*.py' -v
```

The 2026-11-21 recorded suite is 125 passing tests. Windows skips five tests
that require Linux root or Linux file locks; the WSL root run executed all 125.
The raw log is `evidence/final-tests-2026-11-21.json`.

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

Selected `evidence/` files are included for reproducible handover; other local
probe outputs are Git-ignored. These are bounded results, not universal security claims.
Curated handover evidence (all of these paths are unignored and intended for the
repository) includes:

- `final-tests-2026-11-21.json`: 125 passing WSL tests with Python version and raw output.
- `live-all-exercises-2026-11-20.json`: six starter VM runs; four restored workflows.
- `live-burst-ten-2026-11-09.json`: ten admitted requests, eight queued under two workers.
- `live-resource-probe-2026-11-20.json`, `live-security-probe-2026-11-20.json`,
  and `live-network-boundary-2026-11-20.json`: defined boundary probes.
- `security-corpus-2026-11-20.json`: 15 cases across five categories, mixing
  contract and live guest evidence.
- `regression-runs-2026-11-20.jsonl` and `regression-summary-2026-11-21.json`:
  60 no-judge engineering runs and summary.
- `regression-runs-judge-2026-11-21.jsonl` and
  `regression-judge-summary-2026-11-21.json`: same 60 cases with local judge.
- `validation-runs-2026-11-21.jsonl` and `validation-summary-2026-11-21.json`:
  richer 60-case candidate set, model usage, and pre-guard score shifts.
- `validation-injection-guard-retry-2026-11-21.jsonl` and
  `injection-guard-summary-2026-11-21.json`: focused post-guard replay.
- `benchmark-concurrency-2026-11-21.json`: all nine 1/2/4-concurrency batches.

Historical probe outputs in the local `evidence/` directory remain ignored; they
are not prerequisites for the submitted report and should not be added wholesale.

Re-run live probes only from WSL with the prepared root backend and local-only test
fixtures. Do not run these probes against real external services or real credentials.

## Evaluation Data

The 60-row synthetic engineering bank and family-safe 20/40 split are in
`evaluation/regression-bank.json` and `evaluation/regression-split.json`.
They are not 60 independently rated learner submissions. The real evaluation set
and two human rating sets remain pending. Do not use generated examples as human
ratings. Start from
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
  --partition held_out \
  --output evidence/grading-metrics.json
```

Summarize observed runs independently of human labels:

```bash
.venv-linux/bin/python scripts/summarize_runs.py \
  --bank evaluation/regression-bank.json \
  --split evaluation/regression-split.json \
  --runs evidence/regression-runs-2026-11-20.jsonl \
  --output evidence/regression-summary.json
```

The current regression bank covers starter, constant-output, malformed-schema,
runtime-error, and invalid-JSON fixtures. It does not yet cover the PDF's
partly-correct, adversarial, and ambiguous grading cases well enough to be the
final human-labelled evaluation set.

For an unrated validation candidate set with semantic explanation variants,
`scripts/build_validation_bank.py` creates `evaluation/validation-bank.json` and
its frozen 20/40 split without overwriting existing files. The workflow cases
include partly-correct, ambiguous, and grader-injection text while retaining
the real authorized lookup. The two Python tasks have no free-text explanation
field, so their cases remain execution-oriented. The set is synthetic and must
still be independently rated before any grading-quality claim.

After the final bank is frozen and its primary runs are recorded, create one
model-blind packet per independent human rater (use different output files):

```bash
.venv-linux/bin/python scripts/prepare_rating_packet.py \
  --bank evaluation/submissions.json \
  --split evaluation/split-assignments.json \
  --runs evidence/final-runs.jsonl \
  --rater rater-a \
  --output evaluation/rater-a.json
```

The packet includes the task, rubric, submitted source, observed output, and
deterministic evidence, but no model score, automated status, or split assignment.
The script refuses missing runs and existing outputs. Raters must fill criterion
levels and overall decisions independently; adjudicate disagreements afterward.
Blank packets for the current validation bank are already prepared as
`evaluation/rater-a.json` and `evaluation/rater-b.json`. Give each reviewer only
their own copy; these are not completed human labels.
After both are filled, generate a separate adjudication packet (this refuses
blank or malformed ratings and never overwrites an existing file):

```bash
.venv-linux/bin/python scripts/assemble_human_evaluation.py \
  --bank evaluation/validation-bank.json \
  --split evaluation/validation-split.json \
  --rater-a evaluation/rater-a.json --rater-b evaluation/rater-b.json \
  --output evaluation/adjudication.json
```

An independent adjudicator fills `adjudicated_ratings`, `adjudicated_pass`, and
`rationale` for each listed disagreement. Then assemble the preserved original
ratings, decisions, and frozen primary runs, and evaluate **only held-out** rows:

```bash
.venv-linux/bin/python scripts/assemble_human_evaluation.py \
  --bank evaluation/validation-bank.json \
  --split evaluation/validation-split.json \
  --rater-a evaluation/rater-a.json --rater-b evaluation/rater-b.json \
  --adjudication evaluation/adjudication.json \
  --runs evidence/validation-runs-2026-11-21.jsonl \
  --output evaluation/labels.json
.venv-linux/bin/python scripts/evaluate_labels.py \
  --labels evaluation/labels.json --partition held_out \
  --output evidence/grading-held-out-metrics.json
```

The assembler validates the frozen bank digest, row coverage, rater identities,
unchanged submitted code/payload, original decisions, and complete adjudication.
It copies model criterion levels only where actual model judgments exist. A
missing judgment is not invented. The old primary run predates the explicit
injection guard; replay the full held-out bank after calibration before making
final model-quality claims. A local model is **not** an independent human rater.

For a repeatable live request-concurrency benchmark, start the no-model API with
`--workers 4 --tenant-workers 2` and run:

```bash
.venv-linux/bin/python scripts/benchmark_concurrency.py \
  --repeats 3 --output evidence/benchmark-concurrency-2026-11-21.json
```

The recorded 2026-11-21 local trial completed all 21 requests over three rounds
each at offered concurrency 1/2/4 with no queues or failures. Median latencies
were 30.09/30.405/35.535 s and throughput was 0.032/0.066/0.111 requests/s.
This is a small orders-cents load sample, not sustained-load characterization;
hardware, VM memory, snapshot size, and cleanup lag are not in this report.

## Current Limitations

- The ten-request burst completed with two workers. A separate 1/2/4 offered-load
  benchmark with four workers passed, but sustained load, memory/cleanup sampling,
  and ten simultaneous VMs are not measured.
- Learner-writable scratch paths share a 32 MiB tmpfs and the guest root is read-only;
  the live aggregate ENOSPC check passed. This is not the abandoned ext4 user-quota approach.
- The installed Qwen2.5 0.5B judge has a schema-valid two-call smoke test, not
  demonstrated accuracy. Invalid judgments yield **REVIEW**, not a trusted semantic
  score or an infrastructure retry. Human-label calibration remains unmeasured.
- E2B Embed has a desk feasibility comparison in `PROJECT_STATUS.md`, but no local
  deployment or performance benchmark. The current tested backend remains direct
  Firecracker; mentor approval of that choice is still needed.
- The current `evaluation/labels.template.json` is intentionally empty. Collect real
  independent ratings and mentor approval; do not fabricate either.
