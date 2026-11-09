# Compact status and continuation handoff

Updated: 2026-11-09

## Recovery boundary

The previous session is titled "continue where previous work was left off from".
Its transcript was unavailable through the session-history tool. This handoff is
reconstructed from the working tree, [project status](./PROJECT_STATUS.md),
[runbook](./RUNBOOK.md), and saved evidence. It does not claim to preserve unseen
conversation instructions or to compact the application's conversation history.

## Current outcome

The local demonstration has working Firecracker execution, tenant ownership,
bounded admission, deterministic checks, and full workflow snapshot restore.
The complete SRS is not yet accepted. Semantic grading quality and the evaluation
dataset remain the largest gaps.

| Area | Verified state | Remaining limit |
| --- | --- | --- |
| Six exercises | Saved Nov 9 evidence records successful Firecracker execution and deterministic checks for all six starter cases | Starter cases do not establish broad grading accuracy |
| Pause/resume | Four starter workflows restored VM snapshots | Same host and pinned runtime; broader concurrency acceptance remains |
| Admission | Ten simultaneous API submissions completed; eight queued | Two workers, not ten simultaneous VMs; sustained load unmeasured |
| Resources/security | Saved probes cover CPU, RAM, processes, files, output, time, network denial, secret protection, and benign controls | Separate 32 MiB writable disk quota is not enforced; attack corpus incomplete |
| Semantic judge | Invalid rubric output yields REVIEW without an accepted semantic score | Installed Qwen2.5 0.5B has not established grading quality; recorded six-exercise and burst grades are REVIEW |
| Evaluation | Split preparation and metric tooling exist | Submission and label templates are empty; 60 submissions, independent ratings, frozen 20/40 family split, and held-out evaluation remain |

## Verification performed in this continuation

On Windows with the repository Python 3.13.2 virtual environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test*.py' -q
```

Result: **85 tests run, OK, 5 skipped**, in 5.066 seconds. The skipped tests
require Linux/root or Linux file locks. The recorded WSL result is 85 passing
tests; WSL and live Firecracker probes were not rerun during this continuation.

The session metadata reports branch `main`, synchronized with `origin/main`, with
11 pre-existing changed/untracked entries. Those edits remain in place. This
continuation adds this handoff only; it does not commit or publish changes.

## Next work in priority order

1. Assemble the actual 60-submission bank across six exercises and freeze the
   family-safe 20/40 calibration/held-out split before reviewing labels.
2. Collect two independent human ratings, preserving both originals and separate
   adjudication. Do not synthesize human labels or mentor approval.
3. Validate a feasible semantic judge against calibration data, record invalid
   output frequency and runtime/memory/cost, and evaluate the held-out set under
   the frozen protocol.
4. Resolve or explicitly retain the disk-quota limitation, complete the required
   attack corpus, and measure sustained load and concurrent resume behavior.
5. Record the E2B feasibility comparison or backend-selection rationale and team
   member verification evidence required for final acceptance.

Use the current summary at the top of [PROJECT_STATUS.md](./PROJECT_STATUS.md)
and the [RUNBOOK.md](./RUNBOOK.md) commands. Later historical status sections
contain superseded statements and test counts.

## Evidence to reopen

- [All six exercises](./evidence/live-all-exercises-2026-11-09.json)
- [Ten-request burst](./evidence/live-burst-ten-2026-11-09.json)
- [Resource probes](./evidence/live-resource-probe-2026-11-09.json)
- [Security probes](./evidence/live-security-probe-2026-11-09.json)

These evidence files are local and Git-ignored; they are finite observations,
not a universal security guarantee or proof of semantic grading accuracy.
