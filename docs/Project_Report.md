# Secure Multi Tenant Agentic Workflow Sandbox

Project V | Group 44 | CS5903 Distributed AI Training |
Shriiraz Kukatla (CS23BTECH11029) and Asish Mourya Birudu (CS23BTECH11010) |
Repository: https://github.com/AsishMourya/Multi-Tenant-Agentic-Workflow-Sandbox |
Final commit and tag: **pending**; this report reflects the current local implementation.

**Executive summary.** This project investigates whether one local machine can run synthetic learner Python and LangGraph submissions for two tenants while limiting resources and tool access, preserving supported workflow state, and producing auditable grades. The delivered prototype uses Firecracker microVMs, a scoped mock-inventory broker, full same-host snapshots, deterministic checks, and an optional local Qwen2.5 0.5B rubric judge with human review. Six starter exercises completed live VM runs; four workflow starters restored snapshots. A 15-case bounded security corpus passed, and 60-case frozen engineering and validation banks ran without infrastructure errors. The judge is functional but its accuracy is **unvalidated**: the independent human rating packets remain blank, so model-driven decisions are held for review. This is a working local prototype with incomplete grading validation, not a public multi-user service.

## 1. Problem, scope and success criteria

Learners need to execute code and tool-using workflows without being able to inspect another tenant's data, consume unbounded host resources, or reach arbitrary network destinations. Pausing a workflow should free compute without silently losing its supported state. Grading must distinguish exact test failures from semantic quality and must not let a model override mandatory invariants.

The actors are learner tenants A/B, a trusted local control plane/broker, and a human reviewer. The scope is one WSL2/Linux KVM machine, six synthetic exercises (two Python and four workflows), one mock inventory service, and local-only credentials. Public deployment, real secrets, arbitrary package downloads, cross-host migration, and general-purpose agent tools are excluded. The machine must have KVM, root access, and pinned Firecracker artifacts. The acceptance plan is M1-M8 in the original [project understanding](../DAT_Group44.pdf); this report records observed outcomes against those IDs, not a revised approved rubric.

The defined done-when workflow is: authenticate a tenant; create a bounded session; run Python or a workflow in a disposable VM; allow only brokered inventory calls; checkpoint/terminate/restore supported workflows; apply deterministic gates; obtain an optional structured semantic judgment; and retain ambiguous or unvalidated grades for review. The planned M8 targets include a 60-submission set with a family-safe 20/40 calibration/held-out split, two independent human ratings, repeated concurrency 1/2/4 measurements, and a burst of ten. Those are targets, not all achieved results.

## 2. Related work, baselines and alternatives

Firecracker's microVM design [1] motivates the execution boundary; its official snapshot specification [2] informs the same-host, pinned-runtime restore limits. LangGraph's persistence facilities [3] support application-level workflow state but do not by themselves establish restoration of an arbitrary VM process. E2B Embed [4] is a viable higher-level Firecracker stack with additional deployment prerequisites. The project selected direct Firecracker orchestration to keep the local policy and broker explicit, not because E2B was benchmarked and found slower. Shared host Python and containers were lower-effort alternatives but did not match the intended VM boundary. See ADR-001 and ADR-003 in [the ADR log](Architecture_Decision_Records.md).

The working *engineering baseline* is the same frozen 60-case regression bank through the API with the local judge disabled. The submitted-system comparison enables Qwen2.5 0.5B on those same cases. This comparison measures latency, calls, statuses, and snapshot success. It is **not** a deterministic-only versus judge-only versus hybrid grading-accuracy comparison; no human reference labels exist, and hard-failed cases do not receive judge-only assessments. Python packages are pinned in [requirements-lock.txt](../requirements-lock.txt), the web package lock in [web/package-lock.json](../web/package-lock.json), and the VM artifact hashes in [config/firecracker_backend_lock.json](../config/firecracker_backend_lock.json). License inventory and third-party notice review remain to be signed off.

## 3. Architecture and implementation

```architecture
Learner A / Learner B -> React dashboard -> Authenticated API and tenant gateway
API -> admission queue and session state -> Firecracker VM per active submission
VM -> scoped broker -> synthetic inventory fixture
VM -> snapshot manifest and artifacts -> same-host restore
VM output and tool trace -> deterministic checks -> optional local judge -> grade record / review queue
```

The dashboard is a local interface; the bearer token is resolved server-side to a tenant and clients cannot nominate another owner. The [API](../sandbox/api.py), [gateway](../sandbox/tenant_gateway.py), and [platform](../sandbox/platform.py) control admission, session lifecycle, grading, and review. The [backend](../sandbox/firecracker_backend.py) launches the pinned guest, enforces VM and guest resource limits, and keeps direct guest networking disabled. [The broker](../sandbox/broker.py) validates scoped, expiring mock-tool capability requests; real upstream secrets are never passed to learner code. [Snapshot validation](../sandbox/vm_snapshot.py) checks ownership, artifact hashes, policy/runtime compatibility, and single-active-resume constraints. The trusted host stores session and review state in local SQLite under ignored `work/`; learner scratch is a shared 32 MiB guest tmpfs with a read-only root. The central trust boundary is between host control plane/broker and untrusted guest source, output, and tool text. The rubric judge receives bounded evidence, no tools or secrets. The public API is loopback-only and is not hardened for Internet exposure.

## 4. Methodology and experiment setup

Evaluation questions were whether the six exercises execute and restore, whether defined boundary probes are denied while benign controls work, whether bounded admission survives a ten-request burst, what the local judge costs in time and tokens, and whether injected grading instructions change model scores. The [regression bank](../evaluation/regression-bank.json) has 60 synthetic execution-oriented cases, ten per exercise, with a frozen digest and 20/40 family split. The separate [validation candidate bank](../evaluation/validation-bank.json) has 60 synthetic cases including starter, partly-correct, malformed, ambiguous, and adversarial variants; its [split](../evaluation/validation-split.json) is also family-safe 20/40. These are synthetic fixtures, not student submissions. Both primary banks ran once; the concurrency benchmark repeated three rounds at each offered load.

The local host preflight recorded WSL2 x86-64, 16 logical CPUs, about 7.4 GiB RAM, KVM API 12, and the pinned Firecracker binary/kernel/guest image under `/root/dat-backend`. The guest uses Python 3.12 and LangGraph 1.2.2 according to the runtime manifest; the local judge is Qwen2.5 0.5B through Ollama. [The policy](../config/policy.json) specifies one vCPU, 512 MiB VM memory, 15 CPU-seconds, 15 s submission wall time, 16 processes, 64 KiB output, and 32 MiB writable scratch. The Python lock and UI lock define control-plane dependencies. The benchmark server had four global workers and two per-tenant slots; earlier burst evidence used two global workers. Actual benchmark environment and trial results are retained in [the raw benchmark](../evidence/benchmark-concurrency-2026-11-21.json).

Commands to reproduce the defined evidence are in [README](../README.md) and [RUNBOOK](../RUNBOOK.md). Key entry points are `scripts/live_api_workflow_probe.py --exercise all`, `scripts/live_security_probe.py`, `scripts/firecracker_resource_probe.py`, `scripts/run_evaluation.py` with a frozen bank/split, `scripts/summarize_runs.py`, `scripts/benchmark_concurrency.py --repeats 3`, and `scripts/record_tests.py`. Results below refer to saved runs; repeatability on another host is not established. The 60-case judge run is one model sampling pass, not a distribution over seeds. End-to-end latency includes API/session and admission overhead; throughput is completed requests divided by batch wall time.

## 5. Results, observations and analysis

| Scenario and metric | Baseline no judge | Local judge enabled | Runs and source |
|---|---:|---:|---|
| Same 60 regression cases; infrastructure errors | 0 | 0 | 60 each; regression summaries |
| End-to-end median latency | 5.55 s | 5.15 s | 60 each; paired workload, not a causal speedup claim |
| End-to-end p95 latency | 26.16 s | 23.00 s | 60 each; one pass |
| Model calls / provisional scores | 0 / 0 | 22 / 10 | Hard failures were not sent to the model |
| Final statuses FAIL_INVARIANT / REVIEW | 48 / 12 | 48 / 12 | Unvalidated model scores are REVIEW |
| VM snapshot restores | 8 / 8 | 8 / 8 | Recorded snapshot cases only |

Sources: [no-judge raw runs](../evidence/regression-runs-2026-11-20.jsonl), [no-judge summary](../evidence/regression-summary-2026-11-21.json), [judge raw runs](../evidence/regression-runs-judge-2026-11-21.jsonl), [judge summary](../evidence/regression-judge-summary-2026-11-21.json). The median difference is not interpreted as a judge performance benefit: host scheduling and different execution times dominate this small non-randomized run. Two model calls failed evidence validation and stayed in REVIEW.

The richer validation candidate bank completed 60/60 primary runs with zero infrastructure errors: 24 FAIL_INVARIANT and 36 REVIEW. All 32 recorded workflow snapshot restores succeeded. There were 72 model calls, 40,990 prompt tokens, 10,957 completion tokens, 36 provisional scores, 19.15 s median and 21.36 s p95 end-to-end latency. The observed peak model resident value reported by Ollama was 483,645,193 bytes. Eight matched adversarial explanation outputs inflated provisional scores by a mean 12.19 points relative to starter counterparts; two reached 100/100. That failure motivated a narrow explicit-instruction guard. A later focused replay of the eight adversarial cases yielded 8/8 REVIEW, zero provisional scores, zero model calls, and 8/8 restored snapshots. This tests the known wording, not general prompt-injection resistance. See [validation summary](../evidence/validation-summary-2026-11-21.json), [raw runs](../evidence/validation-runs-2026-11-21.jsonl), and [guard replay](../evidence/injection-guard-summary-2026-11-21.json).

```chart
1|30.09|0.032
2|30.405|0.066
4|35.535|0.111
```

Figure 1. Offered concurrency versus median latency and throughput; three rounds at each level. Source: [benchmark](../evidence/benchmark-concurrency-2026-11-21.json).

The three rounds yielded 3, 6, and 12 requests respectively; 21/21 passed with no queueing on the four-worker server. p95 latencies were 33.96, 31.29, and 37.40 s. This sample does not measure sustained load, peak host memory, snapshot size, or cleanup delay. The separate [two-worker ten-request burst](../evidence/live-burst-ten-2026-11-09.json) completed all ten with eight queued; it did not run ten VMs simultaneously.

Six dashboard starter cases completed in Firecracker, all deterministic checks passed, and the four workflow cases restored snapshots. The bounded [security corpus](../evidence/security-corpus-2026-11-20.json) recorded 15/15 passing defined cases, three each for isolation, resource exhaustion, network denial, secret protection, and grader injection; it mixes live guest probes with contract gates. [Resource probes](../evidence/live-resource-probe-2026-11-20.json) covered CPU, memory, wall, process, disk, and output limits with benign controls. This is zero observed failures in those fixtures, not a universal security guarantee. **Human-human agreement, semantic MAE, weighted model-human agreement, pass/fail error rates, and deterministic/judge/hybrid accuracy are not measured.** The [two rating packets](../evaluation/rater-a.json) and [second packet](../evaluation/rater-b.json) remain blank.

## 6. Milestone verification matrix

| ID | Test ID and expected outcome | Observed outcome | Status | Evidence |
|---|---|---|---|---|
| M1 | Six Python/workflow cases execute for isolated tenants | Six starters pass; ownership probes pass | Pass for defined cases | live-all-exercises; security-corpus ISO |
| M2 | CPU, memory, time, process, disk, output and network policy enforced | Defined probes and benign controls pass; 32 MiB tmpfs | Pass for defined cases | live-resource-probe; security-corpus RES/NET |
| M3 | Allowed broker calls work; foreign/expired/disallowed calls fail; canary absent | Contract and guest probes pass | Pass for defined cases | security-corpus SEC; broker tests |
| M4 | VM state/artifacts resume; incompatible reject; compute released | Four starter workflows restored; manifest tests reject invalid states | Partial: same host/pinned runtime; mentor interpretation pending | live-all-exercises; vm_snapshot tests |
| M5 | Burst queues/rejects; restart/expiry cleanup | Ten requests completed with eight queued; recovery tests pass | Pass for bounded test; sustained load not run | live-burst-ten; lifecycle tests |
| M6 | Known correct/incorrect/malformed/timeout deterministic outcomes | 60-case regression and focused tests pass; no-model path available | Pass for defined cases | regression summary; deterministic tests |
| M7 | Real local model rubric plus review | Qwen2.5 0.5B ran; evidence and provisional scores recorded; all unvalidated results held | Partial: accuracy unvalidated | validation summary; review tests |
| M8 | Attack cases, human labels, metrics and baseline comparison | 15-case corpus and engineering/performance results; no human labels or grading-accuracy baselines | Partial | security corpus; summaries; benchmark |

The matrix maps to the project-understanding milestone IDs, not a mentor-approved change. None of the finite tests certifies universal isolation or model reliability.

## 7. Mentor feedback and engineering evolution

| FB-ID | Mentor request | Response and status | Change or justification | Evidence |
|---|---|---|---|---|
| Not available | Scored mentor feedback records are not included in the repository | Traceability pending | Feedback IDs and closure require source records | Repository history and status |
| Not available | Approval for direct Firecracker and M4 fidelity interpretation | Pending | Same-host full VM snapshot implemented; approval not recorded | ADR-001, ADR-003 |

The implementation evolved from the initial design: the exercise set grew to six; guest writable scratch became a bounded shared tmpfs instead of the abandoned ext4 user-quota attempt; a local model replaced mock-only semantic grading; uncalibrated scores were routed to review; and measured adversarial score inflation motivated the explicit-instruction guard. These changes are not attributed to mentor feedback without supporting records. The guide's 9 October methodology record remains historically unverified in ADR-006.

## 8. Current state, limitations and risks

Working within the local test scope: two-tenant API ownership, six live starter exercises, resource and default-deny network probes, mock broker, same-host VM snapshot restoration, bounded admission, deterministic grading, local-model calls, grade audit records, and a review queue. Partially complete: semantic grading quality, calibration, held-out evaluation, sustained-load characterization, cross-host portability, and mentor approval. Missing: two independent completed human rating packets, adjudication, final accuracy baseline comparison, scored-feedback traceability, verified per-student contributions, and final repository tag. Presentation and recording are intentionally outside this report package.

Known risks include the local judge's demonstrated susceptibility to score-changing text; the guard is a narrow heuristic. All model-driven grades stay pending review. WSL2/KVM/root and the pinned guest image are operational dependencies; no public-host security review was performed. Synthetic data may not represent real student submissions. A local model has no API fee but consumes memory and compute. A dependency audit found three issues in the pinned frontend development/build dependency tree (one moderate, two high); the production-only audit found zero. A Vite major-version migration and retest remain pending; the dashboard must stay loopback-only. The report and evidence are local until committed, so links to those files are not yet available from the GitHub revision. Real credentials and learner data are excluded from the repository. Issue tracking for pending work remains to be established.

## 9. Way forward

| Priority | Task and starting point | Dependency or risk | Done when |
|---|---|---|---|
| P1 | Two humans independently complete `evaluation/rater-a.json` and `rater-b.json`; run `scripts/assemble_human_evaluation.py` | Human availability and rubric realism | 60/60 complete, disagreements separately adjudicated, originals preserved |
| P2 | Calibrate on the frozen 20 only, then rerun/evaluate held-out 40 using `scripts/run_evaluation.py` and `scripts/evaluate_labels.py` | P1; avoid held-out leakage | Human-human and model-human agreement, MAE, pass/fail errors, review rate and uncertainty reported |
| P3 | Run identical judge-only/deterministic/hybrid held-out comparison and extended memory/snapshot/cleanup measurements | P1-P2; hardware headroom | Baseline table has identical IDs, repeated trials, raw logs and units |
| P4 | Obtain dated methodology/feedback records, mentor approval, member verification and license review | Team/mentor input | ADR-006 and feedback/contribution table cite actual records |
| P5 | Clean clone, reproduce evidence, review secrets, commit and tag final revision | P1-P4 plus presentation/video outside this package | Clean checkout passes tests and report links resolve at the final SHA/tag |

## 10. Contributions, AI use and attribution

The project understanding identifies Shriiraz Kukatla and Asish Mourya Birudu as team members. Recent Git commits are attributed to `AsishMourya`, but the available history does not establish a reliable module-by-module contribution split or independently verified work for each member. A member-level contribution and verification record, supported by commits or PRs and viva evidence, remains pending.

AI assistance was used for evaluation-bank and rating-packet scripts, adjudication and benchmark tooling, tests, documentation, and code-review suggestions. Verification evidence includes 125 passing WSL tests, a successful frontend build, and saved live Firecracker runs. These checks do not replace review and verification by the project members.

The implementation reuses Python, LangGraph, React/Vite, Firecracker, Ollama, and Qwen2.5 0.5B. Versions are pinned or recorded in the Python/web locks and VM/model run metadata where available. Synthetic exercise fixtures and dummy secrets are project-local. Third-party license notices and model usage terms require a final audit before publication; no unverified compliance claim is made.

## References and appendices

[1] A. Agache et al., "Firecracker: Lightweight Virtualization for Serverless Applications," NSDI 2020. https://www.usenix.org/conference/nsdi20/presentation/agache  

[2] Firecracker Project, "Snapshot Support." https://github.com/firecracker-microvm/firecracker/blob/main/docs/snapshotting/snapshot-support.md  

[3] LangChain, "LangGraph Persistence." https://docs.langchain.com/oss/python/langgraph/persistence  

[4] E2B, "Embed runtime and Compose requirements." https://github.com/e2b-dev/runtime/blob/main/embed/compose/README.md  

[5] Original project understanding and M1-M8 validation plan: `DAT_Group44.pdf`.

Raw data, frozen bank digests, commands, attack definitions, tests, and the ADR log are retained in the repository paths cited above. The presentation, video, final SHA and tag, mentor feedback IDs, and human-grade accuracy results remain pending.

Appendix A, evidence index. The [test-suite log](../evidence/final-tests-2026-11-21.json) records 125 passing WSL tests. The [six-case live run](../evidence/live-all-exercises-2026-11-20.json) contains observable outputs and snapshot flags. The [security corpus](../evidence/security-corpus-2026-11-20.json) gives case IDs and observed values, with supporting resource and network probes in the evidence folder. Frozen bank digests and individual results are retained in the regression and validation JSONL files, not reconstructed from this report. The [benchmark JSON](../evidence/benchmark-concurrency-2026-11-21.json) includes all nine batches and 21 request outcomes. The [guard replay JSON](../evidence/injection-guard-summary-2026-11-21.json) is a post-fix focused test, while the original validation run records the pre-fix score inflation; they must not be presented as one homogeneous experiment.

Appendix B, reproduction boundary. Start the dashboard from WSL Ubuntu with `bash start-demo.sh --offline --with-judge` after the pinned dependencies, KVM artifacts, and local Ollama model are installed. Use `bash start-demo.sh --offline` for the no-model baseline. `config/tenants.local.json` is generated locally and is Git-ignored; never upload it. Run `PYTHONNOUSERSITE=1 .venv-linux/bin/python scripts/record_tests.py --output evidence/final-tests-local.json` as root for the Linux-only tests. Run bank scripts only against the frozen bank/split pair and save new output names; the tools refuse mismatched digests or duplicate primary records. The full run commands and reviewer handoff are in [RUNBOOK](../RUNBOOK.md). The VM binary, kernel, and guest image are large local artifacts and are not embedded in the Git repository; the clean-clone evaluator needs the documented backend setup and a KVM-capable host.
