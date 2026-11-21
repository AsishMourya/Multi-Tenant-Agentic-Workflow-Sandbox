# Architecture Decision Records

**Project:** Secure Multi-Tenant Agentic Workflow Sandbox  
**Course:** CS5903: Distributed AI Training  
**Group:** Project V / Group 44  
**Members:** Shriiraz Kukatla (CS23BTECH11029); Asish Mourya Birudu (CS23BTECH11010)  
**Repository:** https://github.com/AsishMourya/Multi-Tenant-Agentic-Workflow-Sandbox

## Decision index

| ADR | Decision | Status |
|---|---|---|
| ADR-001 | Execute learner code in direct Firecracker microVMs | Accepted for prototype |
| ADR-002 | Deny guest egress; broker scoped synthetic tools | Accepted |
| ADR-003 | Restore supported workflows from same-host VM snapshots | Accepted for pinned host |
| ADR-004 | Bound writable guest storage with a shared 32 MiB tmpfs | Accepted for guest image |
| ADR-005 | Gate semantic judgments with exact checks and human review | Accepted |
| ADR-006 | Separate engineering regression from grading validation | Accepted protocol; labels pending |
| ADR-007 | Record the methodology checkpoint as unverified | Open traceability gap |

---

## ADR-001 — Execute learner code in direct Firecracker microVMs

### Status and scope

accepted for the local prototype; applies
to M1–M5 execution, tenant isolation and lifecycle. Original decision
date is not established. This record does not claim the choice was
approved by a mentor.

### Context and decision drivers

Learners control Python source and workflow instructions. A process can
consume resources, attempt to reach a host service, or try to read data
owned by another tenant. The project must keep user code outside the
trusted API process, bound CPU/memory/time/process/output/scratch use,
and fail closed when the isolation runtime is unavailable. The actual
evaluation host is a single WSL2/Linux machine with KVM and locked
Firecracker artifacts; the setup cannot assume a cloud execution
service.

### Options considered

  - **Shared host interpreter.** Lowest implementation cost and startup
    overhead, but learner code shares the host kernel process and
    filesystem authority. Rejected because it offers no suitable
    hostile-code boundary.

  - **Containers.** Mature packaging and convenient development. They
    share the host kernel, and no container threat model or acceptance
    run was supplied as equivalent to this project boundary. They were
    not benchmarked head-to-head.

  - **Hosted sandbox or E2B Embed.** Potentially reduces local
    orchestration work but requires validated provider access, data
    handling, and service availability; the integration was not
    established in this checkout.

  - **Direct Firecracker.** Requires the team to own launch, device
    setup, guest wrapper, cleanup and snapshot compatibility. It
    provides an inspectable local microVM path aligned with the KVM
    evaluation host.

### Decision and rationale

Use direct Firecracker orchestration with a pinned VMM, kernel and guest
image. Send a submission to a disposable VM only after preflight and
resource policy validation. Treat a missing device/artifact or launch
failure as infrastructure unavailability and fail closed; never silently
execute learner code on the host. The decision is a fit-to-environment
judgement backed by successful live runs, not a measured claim that
Firecracker is more secure or faster than containers or hosted
sandboxes.

### Consequences and trade-offs

The execution boundary is separate from the API process and can apply
VM-level CPU and memory budgets. It adds operational dependence on
root/KVM, WSL2 compatibility, large VM artifacts and cleanup.
Windows-only execution is insufficient for final Linux isolation claims.
Pinning reduces version drift but ties snapshots to the selected
image/VMM. A backend migration requires repeating tenant, resource,
broker and restore acceptance tests. The supported boundary remains a
college prototype; the probes do not demonstrate resistance to every
guest escape or host compromise.

### Evidence and validation

Implementation: 'sandbox/firecracker_backend.py',
'sandbox/guest_runtime.py'; locked artifact digests:
'config/firecracker_backend_lock.json'; live starter outputs:
'evidence/live-all-exercises-2026-11-20.json'; isolation tests:
'tests/test_isolated_submission.py'; readiness tool:
'scripts/feasibility.py'. The README documents WSL2/Ubuntu 22.04 and
'/root/dat-backend' prerequisites.

### Revisit trigger

Revisit if KVM is unavailable on the evaluator's required host, the
pinned backend cannot be rebuilt, or an alternative passes the same
tenant separation, resource, network, tool and snapshot tests with a
lower measured operational burden. A comparative performance or security
claim requires a controlled experiment.

## ADR-002 — Deny guest egress; broker scoped synthetic tools

### Status and scope

accepted; covers M2–M3 guest network and
tool authorization boundaries. 

### Context and decision drivers

Inventory exercises need a narrow lookup capability, but untrusted
learner code must not receive service credentials or freely contact
public endpoints, the host, or another tenant. A client-side wrapper
alone is not enforcement: user code can bypass it. A request must be
authorized for the correct tenant, exercise, operation and time window,
and retries must not duplicate side effects.

### Options considered

  - Put API credentials in the guest and allow direct requests. This is
    flexible and simple for integrations, but creates an exfiltration
    and credential replay path.

  - Allowlist guest destinations. This could support real services, but
    requires independently correct handling of DNS, IPv4/IPv6,
    redirects, host-management addresses and future destinations.

  - Deny general guest egress and mediate a small set of operations
    through a trusted host broker. This narrows the feature set and adds
    broker code, but keeps credentials and policy outside guest control.

### Decision and rationale

General guest networking remains denied. The host broker accepts only
explicitly authorized exercise operations and serves fixed synthetic
inventory records. It checks tenant identity, exercise, allowed
operation, capability expiry and request identity. Replayed request IDs
are handled idempotently. Network-denial evidence and
broker-authorization evidence are separate: a blocked socket probe does
not prove broker correctness, and a permitted mock lookup does not imply
arbitrary egress.

### Consequences and trade-offs

Exercises cannot download packages, call arbitrary APIs or access real
inventory services. Adding a tool requires a declared operation, narrow
request/response schema, tenant binding, expiry/replay policy and
positive/negative tests. Fresh authorization is issued after restore.
Dummy canaries help test known leak paths but are not production secrets
and cannot establish absence of every exfiltration channel. The 20
November network tests exercise finite local IPv4, IPv6 and DNS-shaped
probes; they are not a universal firewall audit.

### Evidence and validation

Broker and policy: 'sandbox/broker.py', 'config/policy.json'; network
boundary: 'evidence/live-network-boundary-2026-11-20.json'; 15-case
security suite: 'evidence/security-corpus-2026-11-20.json'; contracts:
'tests/test_contracts.py'. The recorded network probe includes benign
positive controls and observer checks.

### Revisit trigger

An approved exercise requires an external service and a revised threat
model; destination, DNS/redirect, secret, capability expiry, replay and
cross-tenant tests are added and pass before the new access is enabled.

## ADR-003 — Restore supported work from same-host full VM snapshots

### Status and scope

accepted for supported workflows on the
pinned host; M4 snapshot lifecycle. 

### Context and decision drivers

Pausing a workflow should release active VM compute while preserving
enough state to continue the supported exercise. An application-level
LangGraph checkpoint persists workflow state but does not, by itself,
preserve arbitrary Python process state, guest memory or open runtime
resources. Resume must not transfer tenant ownership, preserve stale
tool capabilities, or allow two concurrent owners to activate the same
snapshot.

### Options considered

  - Keep the VM running while paused: simplest and highest process
    fidelity but continues consuming guest memory and VM resources.

  - Save only an application-level safe point: smaller and more portable
    but requires exercise-specific continuation semantics and does not
    preserve arbitrary guest process state.

  - Save Firecracker machine/memory state and the corresponding disk as
    a unit: supports the tested process continuation path but creates
    large, host/runtime-bound artifacts and requires strong manifest
    validation.

### Decision and rationale

For the supported workflow paths, save the VM and disk artifacts as a
compatible unit, then stop the paused VM. Before resume, validate the
snapshot manifest, session owner, policy/runtime identity, artifact
digests, and a single-active-resume lease. Reissue broker authorization
after restoration rather than reviving pre-pause capability state. Do
not unpickle learner-controlled state in the trusted host. A JSON safe
point may be useful later but is not the basis for current snapshot
results.

### Consequences and trade-offs

The implementation retains tested workflow continuity on the same pinned
host, and pause can release active compute. Snapshot files consume
storage; capture, validation, restore and cleanup add latency and
failure modes. Cross-host transfer, changed Firecracker versions, GPU
continuation, open external connections and arbitrary workloads are not
established. Invalid, foreign, corrupt or policy-mismatched artifacts
must be rejected. A restore failure is infrastructure failure, not a
semantic learner failure.

### Evidence and validation

Implementation: 'sandbox/vm_snapshot.py'; manifest and lifecycle tests:
'tests/test_vm_snapshot.py', 'tests/test_workflow.py'; four of six
recorded starter exercises restored:
'evidence/live-all-exercises-2026-11-20.json'; 32/32 restores in the
saved validation summary: 'evidence/validation-summary-2026-11-21.json'.
These are observed finite runs, not an availability guarantee.

### Revisit trigger

Revisit if a Firecracker/image change fails compatibility tests,
cross-host resume becomes a requirement, snapshot size or restore time
violates a predeclared limit, or an exercise changes its continuation
contract.

## ADR-004 — Bound writable guest storage with a shared 32 MiB tmpfs

### Status and scope

accepted for the pinned guest image; M2
storage policy.

### Context and decision drivers

Untrusted code can write repeatedly, generate temporary files or attempt
to alter runtime files. The initial ext4 user-quota approach did not
provide the intended verified enforcement in the tested guest
configuration. Continuing to describe that setup as quota-limited would
overstate containment. The replacement needs a known aggregate bound and
a mostly read-only base runtime.

### Options considered

  - Keep debugging ext4 user quota: retains per-user semantics, but the
    original configuration was not proven to enforce the intended limit.

  - Use a fixed-size writable ext4 overlay: potentially durable and
    familiar, but requires separate image sizing, cleanup and
    failure-mode validation.

  - Mount a single bounded tmpfs for writable guest scratch and keep the
    root read-only: straightforward aggregate cap and observed
    exhaustion behavior, at the cost of memory-backed storage and no
    independent per-directory quota.

### Decision and rationale

Use a read-only guest root and a shared 32 MiB writable tmpfs for
scratch. The measured disk-flood probes reached the configured limit and
the backend policy constrains the writable bytes to 33,554,432. This
decision follows the failed-to-verify quota path and bounded probes. It
is a local prototype policy, not an assertion that 32 MiB suits all
workloads or constitutes complete filesystem isolation.

### Consequences and trade-offs

Scratch competes with the VM's memory budget and is not durable except
insofar as the supported VM/disk snapshot path captures it. The limit
applies to the shared mount, not a per-user quota. Large legitimate
writes fail; supported exercises must fit. The guest root cannot be
modified by ordinary submissions, but the finite disk probes do not
prove all storage paths are covered. Any increase must be measured
against memory pressure, snapshot cost, cleanup behavior and the
existing 512 MiB guest cap.

### Evidence and validation

Mount and backend code: 'sandbox/guest_runtime.py',
'sandbox/firecracker_backend.py'; policy: 'config/policy.json'; unit
coverage: 'tests/test_disk_limit.py'; live resource probe:
'evidence/live-resource-probe-2026-11-20.json'. The saved probe
reports successful file and aggregate disk limit checks.

### Revisit trigger

A supported exercise needs more durable scratch, the guest memory budget
changes, a new write path bypasses the mount limit, or repeated probes
show unacceptable pressure or cleanup behavior. Any new cap should be
backed by repeated resource evidence.

## ADR-005 — Gate semantic judgments with exact checks and human review

### Status and scope

accepted as the grading safety policy;
M6–M7. Threshold calibration and automatic semantic accuracy remain
pending.

### Context and decision drivers

Arithmetic, schemas, required tool traces and mandatory output
conditions can often be checked exactly. Free-form explanations require
semantic interpretation. A small local model can emit malformed JSON,
inconsistent scores, unsupported evidence or follow instructions
contained in learner output. Infrastructure failure must remain distinct
from an incorrect submission. The design must retain an auditable route
for uncertain output.

### Options considered

  - Deterministic-only evaluation: reproducible for hard constraints but
    cannot evaluate explanation quality.

  - Model-only grading: flexible for prose but exposes mandatory
    decisions to unsupported or adversarial model output.

  - Hybrid exact gates, schema/evidence validation, optional local model
    and human review: preserves reproducible constraints and supports
    semantic assistance, but increases latency and review effort.

### Decision and rationale

Mandatory exact-invariant failure blocks a pass. The optional Qwen2.5
0.5B judge runs locally through Ollama and returns structured rubric
assessments with evidence. Invalid, conflicting, borderline or
evidence-mismatched outputs go to REVIEW. Until independent human labels
support calibration, model-selected semantic PASS/FAIL also remains
REVIEW. A narrow explicit-instruction guard routes known
grading-directed text to REVIEW before invoking the model. The guard is
a targeted regression defense and is not a general prompt-injection
detector.

### Consequences and trade-offs

The project can report provisional scores but does not deliver
unattended semantic grades. Human review is required and adds workload.
Local inference avoids a remote API fee but consumes memory and compute.
One frozen regression comparison recorded 22 judge calls and 10
provisional scores; two responses failed evidence validation and
remained in review. An earlier adversarial run found eight matched cases
with mean score inflation of 12.19 points, including two scores of 100;
the guard replay produced eight REVIEW outcomes and zero model
calls/scores. Neither result establishes broad attack resistance or
grading accuracy.

### Evidence and validation

Grading and review code: 'sandbox/grading.py',
'sandbox/local_judge.py', 'sandbox/reviews.py'; regression
comparison: 'evidence/regression-judge-summary-2026-11-21.json';
adversarial runs: 'evidence/validation-runs-2026-11-21.jsonl'; guard
replay: 'evidence/injection-guard-summary-2026-11-21.json'; tests:
'tests/test_agent_grading.py', 'tests/test_review_queue.py'.

### Revisit trigger

Two independent ratings and adjudication are available; thresholds and
acceptable false-accept/false-reject bounds are predeclared; calibration
occurs on the 20-case partition; and the untouched 40 held-out cases
meet the predeclared metrics with uncertainty intervals. Until then,
retain review routing.

## ADR-006 — Separate engineering regression from grading validation

### Status and scope

accepted evaluation protocol; M8.
Human-label evaluation is incomplete. 

### Context and decision drivers

The 60-case regression bank checks execution and common failures but
does not contain sufficient adjudicated human labels to support semantic
reliability claims. Validation also needs partly correct, ambiguous and
adversarial examples. Near-duplicate or related examples must not cross
calibration and held-out partitions, or calibration will leak
information about the evaluation set. Raw runs should remain
reproducible and retriable infrastructure errors should not be counted
as semantic grading errors.

### Options considered

  - Treat the regression bank's status as grading accuracy: easiest to
    report, but invalid without human reference labels.

  - Gather ad hoc examples after viewing model errors: flexible but
    prone to selection bias, mutable test membership and untraceable
    replay.

  - Maintain a separate versioned validation bank with family-safe
    split, two blinded independent rating packets and adjudication: more
    setup and human labor, but a defensible path to measuring semantic
    performance.

### Decision and rationale

Keep the regression bank solely for engineering no-judge/judge-on
comparisons. Use a separate 60-case candidate validation bank,
family-safe 20-case calibration and 40-case held-out split, plus
independent model-blind ratings and an adjudicated reference set. Keep
the bank/split hashes and raw runs. Do not calculate human agreement,
false-accept rate, false-reject rate or semantic error while rating
packets are blank. Infrastructure retries are reported separately from
evaluated outcomes.

### Consequences and trade-offs

This makes the operational regression result interpretable without
confusing it with semantic quality. Synthetic cases limit external
validity; one pass per configuration does not measure variance; two
raters and adjudication are a labor dependency. Held-out cases cannot be
edited after model errors are viewed. If a defect requires changing the
test bank, create a new version and report the change; do not silently
update a frozen partition. Confidence intervals and repeated held-out
evaluation remain to be completed.

### Evidence and validation

Protocol: 'config/evaluation_protocol.json'; regression bank:
'evaluation/regression-bank.json', 'evaluation/regression-split.json';
validation bank/split: 'evaluation/validation-bank.json',
'evaluation/validation-split.json'; rating packet generation and
assembly: 'scripts/prepare_rating_packet.py',
'scripts/assemble_human_evaluation.py'; current summary:
'evidence/validation-summary-2026-11-21.json'. The packets
'evaluation/rater-a.json' and 'evaluation/rater-b.json' remain blank.

### Revisit trigger

Before labels are revealed, raters identify duplicated case families,
unclear rubric anchors or missing failure classes. If revisions are
required, version and refreeze the bank and split, record new hashes,
and preserve the old version. Begin held-out analysis only after the
rating/adjudication protocol is completed.

## ADR-007 — Record the methodology checkpoint as unverified

### Status and scope

Open historical traceability record; applies to M1–M8 methodology and the
handover requirement. It does not assert an earlier decision, mentor
approval, or backdated acceptance.

### Context and decision drivers

The handover guide requires a record stating whether the method was
reaffirmed or changed by the required methodology checkpoint. The currently
supplied repository and project records do not establish a contemporaneous
reaffirmation, a complete old-to-new methodology log, or mentor approval. A
protocol freeze deadline is not by itself evidence that the approach was
accepted. The current checkout supports technical observations, but it cannot
establish what decision was made by the required checkpoint.

### Options considered

- Infer an earlier decision from current code or configuration: unsupported;
  implementation does not establish approval.
- Infer an earlier rationale from present evidence: risks misrepresenting
  when the evidence was written and whether approval occurred.
- Mark the checkpoint unverified, document the current method, and request
  the missing source: transparent, but leaves the historical requirement open.

### Decision and rationale

Mark the methodology checkpoint **not verified**. The current implementation
method is direct microVM execution, a scoped tool broker, same-host snapshots,
deterministic hard gates, provisional local-model judgment, and separate
engineering and human-validation banks. Available evidence cannot determine
whether that method was fully reaffirmed by the checkpoint or whether it
changed. No approved milestone or frozen-test change is asserted. This record
documents the current evidence without assigning a historical decision date.

### Consequences and trade-offs

This record documents the gap but does not close the guide's historical
approval requirement. Later evidence should be linked to its source and exact
revision. If it shows a change, document the old approach, new evidence,
alternatives, selected approach, milestone/test impact, revised plan, and the
required mentor approval. Preserve the historical timeline and do not infer
missing approval. Until then, acceptance of the current code must not be
represented as mentor sign-off.

### Evidence and validation

Current repository and evaluation protocol:
'config/evaluation_protocol.json'; current implementation and bank
digests in this ADR set and the project report; repository history at
<https://github.com/AsishMourya/Multi-Tenant-Agentic-Workflow-Sandbox/commits/main>.
The source describing the original project plan was not present in the
supplied checkout, and no approval artifact was provided. A commit or current
configuration is not a substitute for that record.

### Revisit trigger

A contemporaneous log, issue, email, mentor review or approved change record
becomes available and can be linked to an exact revision, affected milestones
and frozen acceptance tests. Update the gap status only after verifying the
artifact and its approval provenance.

