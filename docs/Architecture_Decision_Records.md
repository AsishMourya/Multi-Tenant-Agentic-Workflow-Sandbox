# Architecture Decision Records

Project V, Group 44. These records document the implementation as inspected on
2026-11-21. The documentation date is not a claim that a decision was originally
made on that date. No mentor approval is inferred from implementation or tests.

## ADR-001 - Use direct Firecracker microVMs for learner execution

- **Date, status, scope:** Documented 2026-11-21; Accepted in the current prototype,
  mentor approval pending; M1-M5, execution backend. Original decision date is not
  established in the repository.
- **Context and drivers:** The project executes untrusted Python and LangGraph code
  on one machine. Tenant separation, resource controls, default-deny networking,
  and same-host pause/resume are required. The available WSL host has working KVM
  and a pinned Firecracker runtime image.
- **Options considered:** Shared host interpreter (simpler, unacceptable isolation);
  containers (easier setup, weaker boundary for this threat model); E2B Embed
  (higher-level SDK/dashboard, but additional host/network prerequisites and a
  separate integration effort); direct Firecracker (more project-owned lifecycle
  code, but a tested VM boundary and snapshots).
- **Decision and rationale:** Use project-owned direct Firecracker orchestration
  for the local prototype. The decision is based on the existing live VM tests,
  not a performance claim against E2B. No E2B deployment or head-to-head benchmark
  was performed.
- **Consequences and trade-offs:** Requires root/KVM, pinned binary/kernel/image,
  and careful cleanup; cannot run learner code from an ordinary Windows checkout.
  A failed KVM preflight must report unavailable execution, not fall back to host
  Python. A Linux VM host is the portability path.
- **Evidence and validation:** [backend](../sandbox/firecracker_backend.py),
  [backend lock](../config/firecracker_backend_lock.json),
  [six live cases](../evidence/live-all-exercises-2026-11-20.json),
  [resource probes](../evidence/live-resource-probe-2026-11-20.json),
  [tests](../tests/test_isolated_submission.py).
- **Revisit trigger:** KVM cannot be provided on the evaluation host, or a measured
  E2B deployment meets the same policy and checkpoint acceptance checks with
  materially lower operational cost; any fundamental switch needs mentor review.

## ADR-002 - Deny direct guest networking and broker allowed mock tools

- **Date, status, scope:** Documented 2026-11-21; Accepted; M2-M3, tool and network
  boundary. Original decision date not established.
- **Context and drivers:** A workflow must use a mock inventory lookup without
  exposing upstream credentials or giving learner code general network access.
- **Options considered:** Give each guest credentials and outbound networking
  (simpler code, broad exfiltration surface); allowlisted guest egress (more
  flexible, harder to constrain redirects/DNS); no guest network plus a scoped
  host broker (narrow, testable capability boundary).
- **Decision and rationale:** Keep guest networking default-denied. The trusted
  broker validates tenant, operation, expiry, and request identity before serving
  synthetic inventory data. Supported calls are idempotent on retry.
- **Consequences and trade-offs:** Only declared mock tools work; arbitrary
  package downloads and external APIs are out of scope. Capability renewal and
  broker replay require explicit logic. Dummy canaries are test fixtures, not
  permission to use real credentials.
- **Evidence and validation:** [broker](../sandbox/broker.py),
  [policy](../config/policy.json),
  [security corpus](../evidence/security-corpus-2026-11-20.json),
  [broker tests](../tests/test_secret_boundary.py).
- **Revisit trigger:** A new approved exercise requires external access and can
  pass destination-side denial, redirect, secret, and replay tests under a revised
  threat model.

## ADR-003 - Preserve supported progress with full same-host VM snapshots

- **Date, status, scope:** Documented 2026-11-21; Accepted for current same-host
  prototype, mentor interpretation pending; M4. Original decision date not established.
- **Context and drivers:** A paused workflow must release compute yet resume its
  defined files and in-memory state. A LangGraph application checkpoint alone
  cannot establish arbitrary process restoration.
- **Options considered:** Keep idle VMs alive (simple, wastes memory); serialize
  application state at explicit safe points (lower fidelity, cannot claim full VM
  continuation); snapshot Firecracker memory, machine state, and disk together
  (higher fidelity with version and host constraints).
- **Decision and rationale:** Use full same-host snapshots with tenant, runtime,
  policy, and artifact-digest checks. Terminate compute after durable capture;
  permit only one active resume. Reject missing or incompatible artifacts.
- **Consequences and trade-offs:** Snapshot artifacts are large and tied to a
  pinned runtime/host. GPU and live external connection continuity are not
  supported. JSON safe-point fallback remains a declared, unapproved alternative;
  the trusted host must never unpickle learner-controlled state.
- **Evidence and validation:** [snapshot implementation](../sandbox/vm_snapshot.py),
  [snapshot tests](../tests/test_vm_snapshot.py),
  [live restored cases](../evidence/live-all-exercises-2026-11-20.json).
- **Revisit trigger:** Cross-host migration becomes required, snapshot
  compatibility fails after a runtime update, or mentor approval specifies a
  different M4 fidelity contract.

## ADR-004 - Gate grading with deterministic checks and human review

- **Date, status, scope:** Documented 2026-11-21; Accepted as a safety policy;
  M6-M7. Empirical judge calibration is pending.
- **Context and drivers:** Numeric and schema errors can be checked exactly, but
  explanations require rubric judgment. A small local model can be inconsistent
  or influenced by learner text. Infrastructure failure must not become an
  academic failure.
- **Options considered:** Deterministic-only (auditable but misses semantic
  quality); judge-only (broad semantic coverage but can override hard failures);
  hybrid with hard gates and review (more states and reviewer work).
- **Decision and rationale:** Mandatory invariant failures block passing. The
  local Qwen2.5 0.5B judge returns two structured rubric assessments with
  evidence. Invalid/conflicting/borderline output goes to REVIEW. Until human
  calibration is available, every model-driven PASS/FAIL also remains REVIEW.
  An explicit-instruction guard routes detected grader-injection text directly
  to review; it is deliberately not described as a general injection defense.
- **Consequences and trade-offs:** This prevents an unvalidated model from
  automatically deciding grades, at the cost of high review volume. Provisional
  scores are not grading accuracy. A larger/better model may improve quality but
  changes hardware, latency, and validation requirements.
- **Evidence and validation:** [grading path](../sandbox/platform.py),
  [local judge](../sandbox/local_judge.py),
  [validation summary](../evidence/validation-summary-2026-11-21.json),
  [injection replay](../evidence/injection-guard-summary-2026-11-21.json).
- **Revisit trigger:** Two independent human ratings and adjudicated calibration
  demonstrate acceptable errors and agreement; then freeze thresholds and test
  on the untouched held-out 40 before enabling automatic model decisions.

## ADR-005 - Separate engineering regression from frozen grading validation

- **Date, status, scope:** Documented 2026-11-21; Accepted evaluation protocol;
  M8. Final human-label evaluation is pending.
- **Context and drivers:** The first 60-case bank exercises execution failures
  but has too few partly-correct, ambiguous, or adversarial explanations for
  semantic validation. Related variants can leak across train/evaluation splits.
- **Options considered:** Reuse the regression bank as grading evidence (cheap,
  misleading); manually collect ad hoc examples (unfrozen, hard to reproduce);
  freeze a separate synthetic bank by family and hash, then blind-rate it.
- **Decision and rationale:** Keep the original regression bank as an engineering
  baseline. Freeze a separate 60-case candidate bank with a family-safe 20/40
  split. Give model-blind packets to two independent human raters; preserve both
  and adjudicate disagreements separately. Calculate held-out grading metrics
  only after ratings and calibration.
- **Consequences and trade-offs:** Synthetic data limits external validity.
  Human time is a real dependency. The current two packets are blank, so no
  human-human agreement, semantic MAE, or pass/fail accuracy is claimed.
- **Evidence and validation:** [bank](../evaluation/validation-bank.json),
  [split](../evaluation/validation-split.json),
  [packet generator](../scripts/prepare_rating_packet.py),
  [adjudication assembler](../scripts/assemble_human_evaluation.py),
  [evaluation tests](../tests/test_assemble_human_evaluation.py).
- **Revisit trigger:** Raters find poor rubric coverage or duplicated families;
  revise and refreeze before labels are viewed, never silently alter the held-out
  set after evaluation.

## ADR-006 - Record the 9 October methodology checkpoint without backdating

- **Date, status, scope:** Documented 2026-11-21; Pending historical verification;
  methodology across M1-M8. This is not a claim of 9 October approval.
- **Context and drivers:** The course handover guide requires a record of whether
  the method was reaffirmed or changed by 2026-10-09 23:59 IST. The inspected
  checkout and available history do not contain a contemporaneous 9 October
  decision, scored feedback IDs, or mentor sign-off.
- **Options considered:** Assert a retrospective reaffirmation/change without
  evidence (rejected); omit the required record (hides the gap); document the
  missing provenance and request the contemporaneous source (chosen).
- **Decision and rationale:** Do not backdate. The implemented method is direct
  Firecracker plus scoped broker, same-host snapshots, and hybrid review. Whether
  that method was reaffirmed or changed at the checkpoint remains unverified.
  Accordingly no old-approach-to-new-approach timeline or approved milestone
  change can be truthfully reconstructed yet.
- **Consequences and trade-offs:** The submission is transparent but this guide
  requirement is incomplete. If a dated mentor message, review sheet, or team
  record exists, append its actual old approach, new evidence, alternatives,
  selected method, impact, and approval link here without replacing this record.
- **Evidence and validation:** [original project understanding](../DAT_Group44.pdf),
  [current status](../PROJECT_STATUS.md), repository history. These establish the
  plan and current implementation, not the 9 October decision.
- **Revisit trigger:** A verifiable contemporaneous record or mentor confirmation
  is supplied. Record subsequent fundamental changes and approval separately.
