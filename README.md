# Multi-Tenant Agentic Workflow Sandbox

Project V, Group 44 (CS5903). This local prototype runs synthetic Python and
agent-workflow submissions in Firecracker microVMs. An authenticated API owns
tenant sessions, limits resources, brokers approved mock inventory calls, and
records deterministic checks plus optional provisional model judgments. Six
starter exercises run; four workflows restore VM snapshots. Human-labelled
grading accuracy is **not measured**. See the [project report](docs/Project_Report.pdf)
and [architecture decisions](docs/Architecture_Decision_Records.md).

## Requirements and setup

Use Ubuntu 22.04 under WSL2 with root/sudo, writable `/dev/kvm`, Python 3,
Node/npm, and the pinned Firecracker v1.17.0 binary, kernel, and guest image in
`/root/dat-backend`. The VM artifacts are not in Git; their expected names and
SHA-256 hashes are in [config/firecracker_backend_lock.json](config/firecracker_backend_lock.json).
From the repository directory in WSL, check readiness and start the app:

```bash
sudo python3 scripts/feasibility.py --backend-root /root/dat-backend --output /tmp/dat-sandbox-preflight.json
bash start-demo.sh
```

The first online start installs the pinned Python and web dependencies, builds
the dashboard, creates local-only tokens in `config/tenants.local.json`, and
serves the UI and API at <http://127.0.0.1:8080/>. Later starts may use
`bash start-demo.sh --offline`. If KVM or the pinned artifacts are unavailable,
the dashboard may open but learner-code execution fails closed. No database
migration is needed; local SQLite state is initialized in ignored `work/`.
Stop with Ctrl+C. Keep tokens and real learner data out of Git and off a shared
screen.

For the optional local rubric judge, start Ollama, install `qwen2.5:0.5b`, and
launch with `bash start-demo.sh --with-judge` (or add `--offline`). Model scores
remain **REVIEW** until human validation; detected grading instructions in
learner output go directly to review. The judge has no external API fee but
uses host memory and compute.

## Demo

Open the URL above and paste the `tenant-a` token into **Tenant token**.
Run the prefilled **Order totals** example: expect `apple: 250`, `pear: 80`,
and `total_cents: 330`. Next run **Inventory check**: two apples yield seven
available and `accepted: true`. Then run **Stock reorder**: expect
`reorder_quantity: 3`; **Execution details** shows the Firecracker backend,
snapshot restore, and deterministic checks. Change an input and run again to
show that the submission actually executes. Without the judge, a correct run
normally ends in **REVIEW** with exact checks passed; this is expected.

The other exercises are `daily-revenue`, `inventory-brief`, and
`order-explainer`. The request path is dashboard → tenant gateway → admission
queue → Firecracker guest → scoped broker/snapshot → exact checks → optional
judge → persisted review. The guest has no direct network access.

## Test and reproduce evidence

Run these from WSL after the first setup. The full suite needs root for Linux
resource and snapshot tests. The recorded run passed 125 tests; see
[evidence/final-tests-2026-11-21.json](evidence/final-tests-2026-11-21.json).

```bash
sudo -H env PYTHONNOUSERSITE=1 .venv-linux/bin/python -m unittest discover -s tests -q
npm --prefix web run build
npm --prefix web audit
```

To record a fresh test log, replace the first command with
`sudo -H env PYTHONNOUSERSITE=1 .venv-linux/bin/python scripts/record_tests.py --output evidence/final-tests-local.json`.
For a Windows-only contract run, use
`.\.venv\Scripts\python.exe -m unittest discover -s tests -q`; five
Linux-specific tests are skipped there.

With the API running, replay a frozen synthetic bank into a **new** output file,
then summarize it. Keep the original bank and split unchanged:

```bash
.venv-linux/bin/python scripts/run_evaluation.py --bank evaluation/regression-bank.json --split evaluation/regression-split.json --partition all --output evidence/regression-replay-local.jsonl
.venv-linux/bin/python scripts/summarize_runs.py --bank evaluation/regression-bank.json --split evaluation/regression-split.json --runs evidence/regression-replay-local.jsonl --output evidence/regression-replay-summary-local.json
.venv-linux/bin/python scripts/benchmark_concurrency.py --repeats 3 --output evidence/benchmark-local.json
```

The [no-judge](evidence/regression-summary-2026-11-21.json) and
[judge-enabled](evidence/regression-judge-summary-2026-11-21.json) 60-case
summaries compare the same engineering workload, not grading accuracy. The
[validation summary](evidence/validation-summary-2026-11-21.json),
[15-case security corpus](evidence/security-corpus-2026-11-20.json),
[six live starter runs](evidence/live-all-exercises-2026-11-20.json), and
[concurrency benchmark](evidence/benchmark-concurrency-2026-11-21.json) retain
raw results and defined limits. The two independent rating packets are blank;
do not report agreement, semantic error, or pass/fail accuracy from these runs.
Only use synthetic fixtures and local tokens for replay.

## Limits

This is a loopback-only college prototype, not a public deployment. Snapshots
are same-host and pinned-runtime; bounded probes are not proof of universal
isolation or prompt-injection resistance. The full results, limitations, and
remaining M7/M8 work are in the [report](docs/Project_Report.pdf). The report PDF
and ADR log in `docs/` are the submission documents.
