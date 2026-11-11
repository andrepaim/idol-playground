# Character stage coordinator foundation

Status: M2 transition logic, not wired to the authoring API or model workers. It uses [private contracts and storage](character-storage.md). It does not provide process ownership, GPU exclusivity, cancellation/reaping, startup reconciliation or inference resume.

## Claim and cache rules

`StageCoordinator.start` requires a character identity, stage, non-secret material parameters, explicit adapter/model versions and named artifacts from every declared dependency. Input stages additionally require hashes of the original uploads. Other stages cannot supply external upload hashes. The original-upload hashes must appear among the published input artifacts; preprocessing must retain original bytes alongside derivatives.

Dependencies must have succeeded and pass byte verification. Named inputs select material artifacts, excluding coordinator receipts. This avoids invalidating a model merely because an audit timestamp changed. The caller's trusted adapter must declare every relevant input, setting and tool/model version; the helper cannot detect omitted semantic dependencies.

A verified succeeded stage with the same fingerprint returns a cached claim without writing a new revision or launching work. Otherwise the coordinator rejects competing running stages, increments the attempt, invalidates affected descendants and saves running state with revision CAS. The private `_execution.json` receipt records UTC time, input hashes, parameters, versions and the fingerprint. Credentials and raw logs must never be passed as parameters.

Correction examples: body assessment changes preserve the splat/mesh but invalidate downstream assessment/preparation; joint-label changes preserve skin while invalidating motion/package. The stored history and artifacts remain available for inspection. No failed stage is silently accepted because a GLB exists.

## Snapshot validation and completion

`finish` copies worker files through immutable publication, then invokes a trusted **program-defined** validator on those snapshots. Never deserialize a validator or a claim supplied by a browser or reasoning model. Worker outputs cannot use reserved `_execution.json`/`_validation.json` names.

The validator must return an explicit `Decision`:

| Outcome | Stored state | Meaning |
|---|---|---|
| `accept` | `succeeded`, validation passed | All required checks/reviews for this stage passed |
| `review` | `awaiting_review`, validation not passed | Structural requirements passed, but a supported human decision is still needed |
| `reject` | `failed`, validation not passed | The result fails the stage's acceptance criteria |

There is no generic checkbox that promotes rejected geometry into accepted output. The future review API must supply corrected/reviewed parameters and rerun the appropriate validator. A boolean or arbitrary dictionary is not a validation decision. Details must be finite JSON and fit the receipt size bound.

The `_validation.json` receipt binds the decision to exact output hashes and UTC time. It is published separately, then referenced in the same metadata completion commit. The coordinator rechecks claim identity/state/attempt/fingerprint and CAS revision after validation. Late results cannot replace corrections or retries. Modified snapshots fail the store's byte verification rather than acquiring succeeded status.

Private worker originals, rejected output and orphaned copied snapshots are preserved. These are not automatically reusable or approved results. Publication occurs only inside the private store; it does not distribute assets or expose downloads.

## Failure, interruption and integration boundary

`end(claim, state, reason_code)` supports only failed/cancelled/interrupted outcomes with bounded safe reason codes. It cannot bypass validation by setting succeeded status. A superseded claim cannot change a newer attempt. Ordinary validation errors record a safe failure code without copying raw exception text into the audit receipt.

The future process layer must stop/reap a worker before applying cancellation or releasing GPU ownership. This coordinator does not prove a worker has exited. Do not use record state alone to decide a persisted running process is dead. Source/publication I/O errors require the process layer to finish ownership handling and explicitly record/reconcile the attempt.

`CommitUncertain` propagates without a blind failure write: the new validated pointer may already be visible even though directory durability failed. The caller must reconcile/resync before reporting durable completion or retrying. No success is returned after that error.

Current API/defaults, legacy job persistence and actual inference remain unchanged. Process lease/recovery, trusted adapter execution, API/browser integration and real-GPU lifecycle acceptance are subsequent M2 increments. CPU transition tests do not certify CUDA behavior or model/anatomy quality.

## Evidence

Eighteen disposable transition tests first failed on the absent module; explicit external-hash mapping and UTC receipt cases also failed before implementation. Tests cover dependency/input/version errors, verified cache hits, running conflicts, review/rejection, invalid/mutating validators, original-upload mismatch, source preservation, retries, settings-driven invalidation, stale completion before/during validation, durable receipts and post-rename uncertainty. All 126 Python tests and 33 infrastructure tests pass locally; repository CI remains required on the PR and combined commit.
