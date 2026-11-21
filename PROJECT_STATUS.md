# Project Status and Development Plan

Updated: 2026-11-21. Current findings are summarized below. Later sections retain
historical development notes and may not reflect the latest implementation state.

Latest M8 engineering update: a strict assembler now validates two completed
independent rating packets against the frozen bank, generates a separate
adjudication packet for disagreements, and refuses incomplete decisions before
producing labels for held-out metrics. The current packets remain **blank**:
there is still no human agreement or grading-accuracy result. A repeated local
orders-cents benchmark at offered concurrency 1/2/4 (three rounds each, four
configured workers) completed 21/21 Firecracker requests with zero queues or
failures. Median latencies were 30.09/30.405/35.535 s; throughput was
0.032/0.066/0.111 requests/s. This small benchmark does not establish sustained
capacity, memory/cleanup behavior, or ten simultaneous VMs.

M7 update: a real Qwen2.5 0.5B judge has now run through the authenticated
Firecracker API on a learner submission. Two rubric judgments and a provisional
score were persisted. One pre-guard run auto-finalized despite weak model evidence;
the control plane now forces unvalidated local-model PASS/FAIL into REVIEW while
preserving the score and audit trail. A regression test covers this rule. The
dashboard displays both assessments, and `start-demo.sh --with-judge` enables the
local judge when Ollama and the model are available. This is a functional grading
integration, **not** measured judge accuracy.

M8 update: `scripts/summarize_runs.py` validates the frozen bank digest and
deduplicates run records before reporting engineering counts and latency. Its
2026-11-21 summary of the 60 no-model regression runs has 0 infrastructure
errors, median end-to-end latency 5.55 s, p95 26.16 s, and 8/8 recorded snapshot
restores. Human-label metrics remain null. The present bank lacks enough
partly-correct, adversarial, and ambiguous examples for final grading validation.
`scripts/prepare_rating_packet.py` now builds model-blind, unrated packets from a
frozen bank and observed runs for two independent human raters; no ratings have
been supplied or fabricated.
The model-enabled rerun of the 60 engineering cases finished with 0 infrastructure
errors: 48 FAIL_INVARIANT and 12 REVIEW. The model was called 22 times; 2 calls
returned invalid rubric evidence and correctly entered REVIEW. Ten cases retained
a provisional score. The median end-to-end latency was 5.15 s, p95 23.00 s, and
8/8 snapshot runs restored. A later focused live run also recorded two model
prompt/completion token counts and resident model bytes. These numbers are
engineering observations, not human-label accuracy.
An additional, separately frozen 60-case synthetic validation candidate bank is
now in `evaluation/validation-bank.json` with a family-safe 20/40 split in
`evaluation/validation-split.json`. Unlike the engineering bank, its four
workflow exercises include partly-correct, ambiguous, and grader-injection
explanations that preserve the real broker path. All six exercises appear in
both partitions. These are candidates, not human-labelled results.
Two separate, model-blind 60-row rating packets are prepared as
`evaluation/rater-a.json` and `evaluation/rater-b.json`; every rating is null.
The first model-enabled candidate-bank run completed all 60 with 0 infrastructure
errors: 24 FAIL_INVARIANT and 36 REVIEW; 32/32 VM snapshots restored. It recorded
72 judge calls, 40,990 prompt tokens, 10,957 completion tokens, median end-to-end
latency 19.15 s and p95 21.36 s. The eight matched adversarial workflow outputs
raised the provisional score by 12.19 points on average versus clean starters;
two received 100/100. Because those scores were all REVIEW, they were not final
grades, but the score shift demonstrates that the tiny model is not a reliable
injection-resistant grader. The new explicit-instruction pre-judge guard was
then replayed live on all eight adversarial workflow cases: 8/8 REVIEW, 8/8
no provisional score, 8/8 zero judge calls, 8/8 snapshot restores, and 0
infrastructure errors. This is a narrow heuristic, not a general security proof.

This document explains what has been built so far, why it is being tested, what can
be pushed now, and what remains before the project satisfies the complete SRS.

## Current M1–M8 assessment (2026-11-21)

The requirements are **not yet fully done**. Status below distinguishes implementation
and bounded evidence from acceptance at scale; passing the finite probe corpus is not
a universal security claim.

| Requirement | Current status | Evidence and remaining work |
|---|---|---|
| M1 – Isolated execution | Implemented for the six-exercise local demo | `evidence/live-all-exercises-2026-11-20.json` records all six UI starter cases in Firecracker. Earlier overlapping-tenant and owner-denial probes remain bounded local evidence, not a universal isolation proof. |
| M2 – Resource and network policy | Defined live checks pass | The guest now places `/tmp`, `/var/tmp`, `/dev/shm`, and `/run/lock` on one 32 MiB tmpfs and remounts root read-only. `evidence/live-resource-probe-2026-11-20.json` records an aggregate ENOSPC check plus CPU, memory, process, file, output, wall-time, IPv4/IPv6, DNS, and benign-control checks passing. The earlier ext4 user-quota attempt was abandoned; do not describe it as the implemented mechanism. |
| M3 – Secret-safe tool access | Scoped mock broker and defined guest probes pass | `evidence/live-security-probe-2026-11-20.json` and `evidence/live-network-boundary-2026-11-20.json` cover protected files, host-mount absence, canary absence, and host-local network denial. No real credentials or external targets are used. |
| M4 – Stateful pause/resume | Full Firecracker snapshot restore demonstrated | The live workflow runs restore full VM snapshots. Fidelity is same-host and pinned-runtime, not portable across hosts or runtime versions. |
| M5 – Elastic lifecycle | Bounded admission and recovery implemented/tested | The 121-test suite passes in WSL. `evidence/live-burst-ten-2026-11-09.json` records ten simultaneous API requests across two tenants, eight queued and all completed with two workers. Sustained load and ten concurrent VMs remain unmeasured. |
| M6 – Deterministic grading | Six live starter cases plus a 60-row engineering regression run | `evidence/live-all-exercises-2026-11-20.json` records the starter runs. `evaluation/regression-bank.json` is balanced at ten synthetic cases per exercise; `evidence/regression-runs-2026-11-20.jsonl` records 60 Firecracker submissions (12 REVIEW, 48 FAIL_INVARIANT, no infrastructure errors). These are not human-labelled grading accuracy results. |
| M7 – Semantic grading and escalation | Real local judge integrated; quality unvalidated | A Qwen2.5 0.5B run through the authenticated Firecracker API persisted two rubric judgments and a score. Uncalibrated model results now require REVIEW even when their provisional score would PASS/FAIL; human review remains available. Two independent human ratings and calibration remain missing. |
| M8 – Security and grading validation | Security corpus, engineering summary, and richer unrated candidate bank; human evaluation incomplete | `evidence/security-corpus-2026-11-20.json` records 15 passing cases, three in each of five categories, mixing live guest checks and contract gates. `evidence/regression-summary-2026-11-21.json` reports 60 frozen-bank execution outcomes and latency, not grading accuracy. A separate validation candidate bank now includes semantic variants. Human agreement, held-out accuracy, repeated judge comparison, and mentor approval remain outstanding. |

### Remaining work, in priority order

1. Review the 60-case validation candidate bank for rubric coverage and realism.
   Its family-safe 20/40 split is frozen. Collect two independent human ratings
   per row and preserve both original files plus separate adjudication. The older
   engineering regression bank is not a substitute.
2. Calibrate the semantic judge on the 20-row calibration partition only, then run
   the 40 held-out submissions without changing the rubric or prompt. Record repeated
   judge runs, review decisions, human agreement, error rates, latency, and memory.
3. If the presentation or mentor requires stronger scalability evidence, run sustained
   load and explicitly distinguish ten admitted requests from ten concurrent VMs.
4. Obtain mentor approval for the direct-Firecracker and checkpoint approach. An
   E2B Embed desk comparison is recorded below; an E2B deployment/benchmark is not.

### E2B Embed feasibility (desk comparison, not a benchmark)

[E2B Embed](https://github.com/e2b-dev/runtime/blob/main/embed/README.md) is an
open-source single-machine Firecracker stack with an SDK, dashboard, template builds,
and pause/resume. Its [Compose requirements](https://github.com/e2b-dev/runtime/blob/main/embed/compose/README.md)
call for a dedicated Linux KVM host with `/dev/net/tun`, Docker Engine/Compose,
about 12 GiB recommended RAM, and 20 GiB free disk; setup changes host networking,
kernel modules, and system configuration. The current WSL preflight reported about
7.4 GiB RAM and working KVM, but did not establish the other prerequisites. The
[product announcement](https://e2b.dev/resources/introducing-e2b-embed) also says
Embed does not include its secrets, volumes, workload-identity, or proxy features.

Inference: retain the already-tested direct-Firecracker backend for this local
college demo, where the trusted broker and no-network policy are project-owned.
Evaluate E2B Embed separately on a disposable dedicated host if the mentor requires
a product comparison. No E2B deployment, latency result, or equivalent policy claim
is made here.

The label evaluator reports human agreement/disagreement, separates and excludes
infrastructure retries from grading rates, and now supports criterion-level semantic
MAE plus submission-level bootstrap intervals. Optional `run_metrics` inputs produce
judge-call, latency, inference-memory, and cost means with submission-level bootstrap
intervals. The authenticated API's HTTP route and the trusted demo are now exercised by
tests; the API-side SQLite connections are configured for threaded requests, and
per-session duplicate submissions are serialized. A local judge runtime outage produces
`RETRY_ERROR`; an invalid model judgment produces `REVIEW` without a semantic score.
The enforced Firecracker CPU, RAM, address-space, wall-time, process, per-file, and
aggregate scratch-space limits are reflected in `config/policy.json`. The 32 MiB
scratch limit is a guest tmpfs, not an ext4 user quota.
`scripts/prepare_evaluation.py` assigns the frozen 20/40 family split from an actual
60-row bank without reading labels. The current test suite contains 105 tests; all
pass in WSL as root. On Windows,
five Linux-root/file-lock tests are expected to skip. Measurements beyond the
two-call judge smoke test remain absent until labels and repeated-run metric records
are collected. The 60-submission target and family-level split are not yet complete.

## 1. Project Goal

The project is a small single-machine learning platform for two synthetic tenants.
Each tenant should eventually be able to submit bounded Python or LangGraph work,
use only authorized tools, pause and resume supported progress, and receive an
auditable hybrid grade.

The initial implementation began with two exercises; the registered evaluation scope
now includes six:

- tenants `tenant-a` and `tenant-b`;
- Python: `orders-cents`, `daily-revenue`;
- LangGraph: `inventory`, `stock-reorder`, `inventory-brief`, `order-explainer`;
- one local inventory mock service;
- one pinned Python/LangGraph runtime image;
- a CLI or small API;
- project-owned policy, tenant authorization, broker, grading, checkpoint, and review logic.

Remaining exercises, cluster orchestration, warm pools, GPUs, public deployment,
real credentials, package downloads, and judge training are future work.

## 2. What Has Been Implemented

### Platform composition

`sandbox/platform.py` and the authenticated HTTP API create tenant-owned sessions,
execute submitted source through the configured backend, record traces, and create
grade records. The API accepts configured demo credentials and locally registered
accounts; worker/queue settings limit concurrency.

This is a composition layer for development. It is not yet an HTTP service and it
does not execute arbitrary student code.

### Tenant and broker controls

`sandbox/broker.py` implements a local scoped mock broker with:

- tenant/session/exercise binding;
- signed short-lived capabilities;
- operation allowlisting;
- strict inventory arguments;
- expiry and epoch revocation;
- request-ID replay protection;
- changed-payload replay rejection;
- a session call budget;
- audit rows;
- a synthetic upstream canary that is not returned to users.

The trusted principal currently comes from the local controller. Authenticated network
transport is a future implementation step.

### Lifecycle and state

`sandbox/lifecycle.py` implements SQLite-backed states, ownership checks, versions,
idempotency keys, and durable-pause guards.

`sandbox/state.py` implements the current M4 fallback contract,
`inventory-safe-point-1`. It atomically stores only:

```json
{"sku": "apple|pear", "quantity": 0..100, "available": 0..100}
```

The platform pauses after the broker lookup, releases the logical execution slot,
can be restarted, validates the checkpoint owner/version, resumes, and issues a fresh
broker capability. The broker request ID prevents repeating the lookup.

This is application-state recovery. It is not arbitrary Python process restoration,
full microVM restoration, RNG restoration, or restoration of undeclared state.
Mentor approval is still required before treating this as the final M4 interpretation.

`sandbox/snapshots.py` is retained as a platform-independent atomic snapshot-bundle
foundation for later backend integration. It is not currently connected to a real
sandbox runtime.

### Exercises and grading

`exercises/` contains six exercise manifests and trusted references. The original
orders and inventory tasks have live Firecracker evidence. Four newer tasks have
reference, schema, deterministic-grade, and mocked-controller tests; live guest runs
are still required before claiming equal runtime evidence.

`sandbox/grading.py` combines deterministic results with two validated rubric judgments.
It escalates malformed, conflicting, borderline, or evidence-conflicting outcomes to
review. `scripts/prototype.py` creates a demonstration review record.

### Schemas and policy

`schemas/` defines the versioned contracts for exercises, outputs, judges, grades,
policies, and attack cases.

`config/policy.json` records the intended defaults: one vCPU and 128 MiB per small
session, bounded wall time/processes/disk/output, two global active sessions, one
per tenant, deny-by-default networking, and one named broker operation. These values
are design defaults until an execution backend enforces them.

`config/evaluation_protocol.json` freezes D/S normalization, NOT_APPLICABLE and
ABSTAIN handling, hard-gate precedence, the two-judge baseline, the adaptive-call
comparison, the six-exercise/60-submission target, family-level splits, preservation
of both raw human ratings, metric denominators, repeats, uncertainty, and local-judge
feasibility measurements. It does not fabricate the missing labels or split assignments.
`scripts/prepare_evaluation.py` creates the frozen family-level assignment from a
completed 60-row submission bank. It reads only IDs, family IDs, and exercise IDs;
the actual bank and human ratings remain uncollected.

## 3. What We Test Now

Run the full suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v
```

The current suite has 83 passing tests in WSL as root and 83 tests with 5 expected
Linux-only skips on Windows (Ubuntu 22.04). It includes HTTP API/dashboard integration, trusted demo, concurrent
duplicate-submission, judge-outage, and resource-probe contract regressions. The live
Firecracker probe still requires a Linux host with KVM and prepared backend artifacts.

### Contract tests

`tests/test_contracts.py` checks broker authorization, expiry, revocation, replay,
secret protection, lifecycle transitions, Python reference behavior, grading gates,
and judge escalation.

These tests answer: does the project-owned policy logic behave correctly for valid
and invalid requests?

### Workflow tests

`tests/test_workflow.py` checks LangGraph validation, authorized lookup, checkpoint
continuation, insufficient stock, invalid input, and no duplicate lookup.

These tests answer: does the supported workflow behave correctly before backend
integration?

### Platform tests

`tests/test_platform.py` checks two tenants, two exercises, ownership denial, review
records, safe-point persistence, controller restart, resume, and fresh authorization.

These tests answer: does the first complete project flow compose correctly?

### Schema tests

`tests/test_schemas.py` checks manifest structure, schema syntax, policy/attack data,
and known reference outputs.

These tests answer: are the contracts stable enough for later API and grader adapters?

### Snapshot tests

`tests/test_snapshots.py` checks atomic bundle publication, ownership, integrity,
corruption rejection, interruption recovery, and immutable published artifacts.

These tests answer: is the snapshot foundation safe to connect to a backend later?

### Attack fixtures

Run:

```powershell
.\.venv\Scripts\python.exe scripts/attack_cases.py --output evidence/attacks.json
```

The stable cases are:

- `ISO-01`: control-plane cross-tenant access;
- `RES-01`: bounded host watchdog process;
- `NET-01`: unauthorized broker operation and positive control;
- `SEC-01`: synthetic secret protection and revoked capability;
- `GRD-01`: grader-injection text cannot bypass a mandatory invariant.

These are safe control-plane fixtures. They do not prove VM filesystem isolation,
kernel egress filtering, guest memory limits, or real-model robustness.

### Grading protocol tests

The grading tests verify that infrastructure failure precedes policy failure, policy
failure precedes mandatory-invariant failure, and judge output cannot bypass those
gates. They also verify weighted D normalization, weighted applicable S normalization,
NOT_APPLICABLE exclusion only when both judges agree, and REVIEW for abstention or
no applicable semantic evidence.

## 4. Why Testing Is Layered

The SRS treats submitted code, files, prompts, tools, and explanations as untrusted.
Testing therefore has to happen in layers:

1. **Pure contracts** catch ownership, schema, replay, grading, and lifecycle mistakes
   before any sandbox is involved.
2. **The local platform flow** catches integration mistakes between lifecycle, broker,
   checkpoint, exercise, and grading components.
3. **Backend tests** must later catch guest escape, resource exhaustion, network bypass,
   management-port exposure, cleanup failures, and real process-death restoration.
4. **Evaluation tests** must compare deterministic grading, model grading, and human
   review on labelled examples.

Passing the current tests supports only the current contract claims. It is not a claim
of universal sandbox security.

## 5. Windows and WSL Responsibilities

### Windows

Windows is currently used for fast development and contract tests:

- Python and LangGraph logic;
- broker and lifecycle behavior;
- schema and grading checks;
- the trusted CLI demonstration;
- checkpoint restart tests.

These tests do not run arbitrary student code.

### WSL/Linux

WSL/Linux is needed for the backend spike and real isolation work:

- `/dev/kvm` access;
- Firecracker or E2B evaluation;
- Linux cgroups and namespaces;
- network namespace and deny-by-default rules;
- disposable guest execution;
- actual CPU, memory, process, disk, output, and wall-clock enforcement.

Use WSL to run the current tests as a Linux compatibility check:

```bash
cd /mnt/c/Users/asish/OneDrive/Documents/College/7/DAT
python3 -m venv .venv-linux
.venv-linux/bin/python -m pip install -r requirements-lock.txt
.venv-linux/bin/python -m unittest discover -s tests -p 'test*.py' -v
```

Check backend prerequisites:

```bash
ls -l /dev/kvm
test -r /dev/kvm && echo "KVM available" || echo "KVM unavailable"
egrep -c '(vmx|svm)' /proc/cpuinfo
free -h
nproc
```

A laptop with 16 GB RAM is sufficient for the current two-session prototype. A GPU
or external server is not required. A second laptop can be used for independent
validation, judge benchmarking, or documentation, but the final demonstration remains
single-machine unless the SRS is explicitly changed.

## 6. What Can Be Pushed Now

The source-level GitHub push should contain:

- `README.md`;
- `SRS.md`;
- `DAT_ProjectV.pdf`;
- `RUNBOOK.md`;
- `.gitignore`;
- dependency files;
- `attacks/`, `config/`, `exercises/`, `sandbox/`, `schemas/`, `scripts/`, and `tests/`.

Do not push virtual environments, generated `evidence/`, SQLite files, VM images,
model files, scratch work, secrets, or downloaded backend runtimes.

The original PDF is preserved as the source requirements document. `SRS.md` is the
short working version used during implementation.

## 7. Future Implementation Order

### Step 1: backend feasibility

Evaluate E2B Runtime/Embed first on Linux/KVM. Pin a release/commit and record the
image/runtime requirements locally. Keep management ports and install-level credentials
outside guests.

If E2B is infeasible, evaluate OpenSandbox with Docker/gVisor. Select one backend;
do not build both as final platforms.

### Step 2: authenticated API

Add a small API around `Platform` for session creation, status, output, pause, resume,
delete, grades, and reviewer decisions. Identity must come from authentication, not
from an untrusted tenant field.

### Step 3: real guest execution

Replace trusted reference calls with two disposable guest sessions. Use one pinned
Python/LangGraph image. Keep tests, expected answers, databases, keys, snapshots, and
management interfaces outside guest access.

### Step 4: enforce policy

Implement CPU, memory, process, wall-clock, writable-disk, output, and deny-by-default
network limits. Add a concurrent benign task to resource and attack tests.

### Step 5: lifecycle operations

Add bounded admission, per-tenant fairness, leases, cleanup, expiry, crash reconciliation,
and no-orphan checks.

### Step 6: grading isolation

Run deterministic grading in a separate disposable environment. Separate academic
failure, policy failure, and infrastructure retry/error states.

### Step 7: local judge feasibility now

Run one real local-model exercise now and record model/version/quantization/runtime,
cold and warm latency, peak memory, and JSON validity. Reserve judge capacity
separately from execution workers. A mock judge remains integration-only.

### Step 8: integrated semantic evaluation in W5

Run a real local judge with no tools or secrets. Create human labels, calibration data,
held-out examples, agreement metrics, review rate, latency, and resource measurements
using `config/evaluation_protocol.json`. The target remains six exercises and 60
submissions: 20 calibration and 40 family-level held-out submissions. Preserve both
independent ratings separately from the adjudicated label.

### Step 9: expand scope

Only after the first complete isolated flow works should the project add more exercises,
more attack cases, larger evaluation datasets, or optional infrastructure features.

## 8. Claims We Can Make Now

authorization behavior. The updated live resource probe includes a concurrent benign
tenant control, but that version has not yet been run on a KVM host.
We can claim that the project-owned contracts and trusted two-tenant demonstration
pass the current 78-test suite in WSL as root, including the Linux guest-limit and
resume-lock checks. A Windows run passes 83 tests with five expected environment skips.
The Nov 9 live resource probe includes the concurrent benign tenant control and passed
its defined checks.

evaluation set for grading validation; checked-in historical live evidence is bounded
to the scenarios and date recorded in each artifact.
We cannot claim universal isolation, a separately enforced writable-disk quota, broad
burst-load capacity, or semantic-judge reliability. Current live evidence is bounded
to the scenarios and dates recorded in each artifact; grading reliability still
requires human-labelled calibration and held-out evaluation.

## 9. W1 Review Questions and Evidence Answers

### W1-1. New evidence after Week 0 and feedback closure

The current checkout contains these post-Week-0 artifacts:

- 83 passing tests in WSL root, including guest limits, resume locking, and six-exercise registry integration;
- authenticated API plus two overlapping tenant runs using Firecracker;
- Python and workflow full-VM snapshot restore with compute release;
- live CPU/memory/process/file/output/time and IPv4/IPv6/DNS checks with a benign concurrent tenant;
- live guest protection, broker-bypass denial, and canary-absence probes;
- family-level 20/40 split preparation that does not read or fabricate labels;
- local Qwen/Ollama JSON smoke measurement.

The supplied report and current checkout do not define stable feedback IDs. Therefore
no artificial ID mapping is claimed. The evidence closes feedback by topic: tenant
ownership, broker scope/revocation, checkpoint version/ownership, grading precedence,
and repository scope. Backend isolation, resource enforcement, measured judge quality,
and member verification remain open rather than being marked closed.

### W1-2. Clean checkout and selected OSS sandbox

Firecracker is integrated and has live WSL/KVM evidence. A clean checkout can install
dependencies and run the contract suite, but it does not contain the pinned VM binary,
kernel, or guest image; those must be prepared under `/root/dat-backend`. E2B has not
been evaluated, despite the later reuse recommendation. The current backend is direct
Firecracker, not E2B/OpenSandbox.

### W1-3. Snapshot fidelity commitment

The current implementation uses full Firecracker VM snapshots with the matching
`disk.ext4` and verified manifest, on the same host and pinned runtime. Nov 4/9 live
evidence records restored Python/workflow state after compute release. This is not
cross-host or cross-version restoration. Safe-point JSON remains a fallback only and
requires mentor approval; it is not the current primary path.

### W1-4. Failed disk publication and concurrent resume

If disk copy or manifest publication fails, the snapshot stays unpublished and
incomplete staging is rejected/recovered; interruption tests cover this. The backend
uses an exclusive file-lock resume lease so only one restore is active for a snapshot.
That lock test passes in WSL; Windows skips it because Windows lacks the Linux file-lock
implementation used by the backend.

### W1-5. Old capability recovered from VM memory

An old capability cannot authorize after pause/termination: the trusted broker checks
signature, tenant/session/exercise, running state, epoch, expiry, operation, and
arguments. Firecracker guests have no network interface; only the host-mediated named
broker path is available. The live guest security probe covers direct bypass and canary
absence; arbitrary VM-memory forensic extraction is outside the tested corpus.

### W1-6. Durable record preventing repeated effects

The broker SQLite `calls` table stores session, epoch, request ID, argument digest, and
result. Its durable uniqueness key is `(session, request)`, so a retry after capability
renewal returns the cached result instead of repeating the local inventory effect.
Cross-epoch replay is covered by a regression test.

This is sufficient for the current local mock operation. External side effects would
need an upstream effect/outbox protocol; the project does not claim universal exactly-once
delivery.

### W1-7. Actual hardware/model evidence

The Nov 9 smoke record uses `qwen2.5:0.5b` through Ollama: two valid JSON outputs,
about 5.93 seconds for the first call and 0.41 seconds for the second. It is not a
quality test. That record omits measured host memory, peak inference memory, and an
explicit quantization digest. Human-labelled accuracy/agreement and judge capacity
reservation remain open; no GPU is required.

### W1-8. AI-assisted module verification

No member-level verification record exists in the current repository. It would be
untrue to assign modules or claim that either member can explain and modify an
evaluator-selected component.

Before submission, record for each member: name, verified module, commit or test used,
questions asked, and the member's independent modification. A suitable split is
broker/lifecycle/checkpoint for one member and grading/schema/evaluation protocol for
the other, but that assignment must be confirmed by the team rather than fabricated.

## 10. W0 Review Questions and Evidence Answers

### W0-1. Did Firecracker run on the available machine?

Yes. Firecracker v1.17.0 runs in root WSL with the pinned kernel/image; current
evidence includes API-backed workflow execution, full snapshot restore, bounded
resource probes, and cleanup. The service requires root/KVM and prepared artifacts.

### W0-2. What files make one restorable snapshot?

`machine.vmstate`, `memory.mem`, `disk.ext4`, and `manifest.json`. Capture occurs
while paused; files are non-empty, fsynced, hashed, and published by atomic directory
rename. The manifest records owner, session, compatibility, policy, sizes, and hashes.

### W0-3. What if memory succeeds but disk publication fails?

The bundle remains unpublished. Recovery discards staging, leaves the source disk and
existing snapshots unchanged, and restore rejects incomplete artifacts. Interruption
tests cover this path.

### W0-4. What network/vsock state survives restore?

No live external connection continuity is promised. Network policy is reapplied and
broker authorization is renewed. The smoke test had no guest NIC; sockets, DNS state,
peer sessions, and live vsock-style connections are not declared restored state.

### W0-5. How is a broker capability isolated from another session?

The HMAC-signed capability binds tenant, session, exercise, issuer, audience, expiry,
and epoch. The broker also compares the trusted principal against every scope field;
a token from another session is rejected.

### W0-6. What prevents two concurrent resumes?

An exclusive snapshot resume file lock permits one active restore. The lock test passes
in WSL; the broader parallel HTTP resume test is still important for final backend
acceptance.

### W0-7. Can malicious archives, filenames, or symlinks escape artifacts?

The snapshot store does not load arbitrary archives. IDs are restricted, symlinked
bundles/files are rejected, artifact names are fixed, and the manifest must match the
exact artifact set and hashes. Full hostile archive and tenant-directory tests remain
pending for the selected backend.

### W0-8. Why use 60:40 deterministic/semantic weights?

It is a provisional exercise-grade policy: deterministic evidence protects correctness,
tool traces, and mandatory invariants; semantic scoring covers explanation quality. It
is not the DAT course grading formula. Calibration and held-out error analysis can
change it under the frozen protocol.

### W0-9. What evidence determines the escalation threshold?

No empirical threshold is established yet. Current values are provisional: pass at 60,
review within 5 points, disagreement above one level, invalid output, or test conflict.
The 20 calibration submissions may tune them; the 40 family-level held-out submissions
must remain untouched for final error estimates.

### W0-10. Who can see outputs and audit records?

An authenticated tenant can read only its session status/result; that result currently
includes output, grade, and trace. Broker authorization audit rows remain in the
server-side SQLite store. Separate mentor and administrator roles/views are not yet
implemented, and there is no dedicated audit UI.

### W0-11. What security claim follows if all attacks pass?

Only zero observed breaches in the defined, bounded attack corpus under its stated
assumptions. It is not a universal sandbox-security guarantee.

### W0-12. What triggers and how is the safe-point fallback reported?

A reproducible full-backend failure in snapshot compatibility, coherent disk capture,
or restore on the selected host triggers fallback discussion. No such failure is shown
in the current Firecracker probes, so the fallback is not triggered. Mentor approval
is still required. If adopted, report exact fields/node, compute-release point, auth
renewal, deduplication, and excluded state; call it application-state recovery, never
full-VM restore.
