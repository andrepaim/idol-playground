# Image-to-playable implementation progress

Implementation authorized 2026-11-11. Roadmap: [architecture](image-to-playable-plan.md), [milestones](image-to-playable-milestones.md), [acceptance](image-to-playable-validation.md).

## M0 baseline and decision record

Baseline revision: `357262c` (plan integration; runtime unchanged from `49793c4`). This is a partial M0 receipt, not full milestone acceptance.

### Scope decisions

- First runtime: desktop Chromium, one existing reviewed canine, simple flat scene with walls/obstacles, keyboard movement, camera, reset and standing-hold/walk transition. Standing hold is explicitly experimental.
- Convention: runtime uses right-handed Y-up metres; import normalization and original-to-runtime transform must be explicit. Existing walking exports require inspection rather than assumptions about source axes.
- Translation: in-place clip with controller-owned travel; forward exports stay separate. No double application of root movement.
- Adopt the proposed T1/T2/T3 corpus, correction allowance, geometry/rig/contact thresholds and visual rubric as initial acceptance requirements. Runtime budgets freeze on the M1 development baseline before acceptance; no existing performance claim.
- T0 may use the dense private dog. T1's 100,000-triangle ceiling remains required; do not treat T0 as mesh-preparation acceptance.
- Manual anatomy selection is the initial fallback. No paid reasoning provider, personal-image transfer, new cloud backend, deployment or release is enabled.
- Keep all source uploads, original meshes and model caches. Store new experiments in isolated ignored directories; do not republish private artifacts.

### Repository audit

| Area | Baseline fact | Remaining acceptance |
|---|---|---|
| Idol | Setup/readiness and isolated smoke infrastructure exist | Corpus quality and full stage measurements |
| Reconstruction | Calibrated views, stereo and vertex-colored surface export exist | Required anatomy, preparation and runtime budget |
| Rig | Skeleton/skin and three authoring export formats exist | Semantic roles, robust correction and deformation quality |
| Canine walking | One reviewed hierarchy, limited paw remapping, in-place/forward exports exist | Natural rear-leg deformation, generic mapping and gameplay acceptance |
| Viewer | Preview/playback/turntable exist | Player controls, controller/collision, reusable sample |
| Persistence | Terminal job records exist | Atomic durable stages, interruption recovery and dependency invalidation |

Issue reconciliation follows the [milestone matrix](image-to-playable-milestones.md#4-existing-issue-reconciliation). No existing parent is closed by this audit. The implementation request authorizes the relevant roadmap scope; old authorization labels must be reconciled when selecting each issue, not treated as proof that its acceptance has passed.

### Environment observation

Observed 2026-11-11: loopback app `/api/status` reports no active job, no loaded Idol model, all splat/mesh/rig/walk stages ready. NVIDIA reports an RTX 3060 with 12,288 MiB and driver 610.88 (WSL user-space utility reports 610.57.01). The device also serves display workloads; device memory/use is not attributable solely to this app. Existing idle app remains running and is not restarted for this audit.

Historical receipts are local ignored evidence. A prior reviewed dog has 314,023 vertices and 627,159 triangles, vertex colors and 38 exported joints including controls. Those figures explain the preparation dependency; they do not validate changed code. Previous contact metrics were restricted to selected paw regions and do not certify anatomy or natural motion.

Fresh isolated synthetic Idol smoke passed on `357262c` with clean tracked files: PyTorch 2.15.0+cu132, CUDA 13.2, synthetic mode, 10 steps, 65,536 Gaussians, seed 42. Total 50.7 seconds; load 16.547 s, preprocessing 3.163 s, encode 1.819 s, sampling 26.918 s, decode 0.783 s, save 0.098 s. Peak PyTorch allocated memory was 5,094 MiB, not total device memory. Binary PLY integrity and all 65,536 finite positions passed. Full pinned model revisions/settings remain in the ignored `.local/m0-gpu-receipt.json` in the M0 worktree. Synthetic shape inference tests loading and PLY integrity only; it does not satisfy the image-character corpus.

### Corpus and evidence gaps

The existing owner dog and generated derivatives may be used for local regression; no redistribution rights are inferred. Public CI must use authored procedural fixtures with documented provenance. The complete 18 land images, nine swimmer images and annotated held-out split are not yet assembled. Nine independently authored drawing cases now have a pre-inference frozen development/held-out split; source/license and quality limits are recorded in the [development baseline](character-baseline.md). Do not fabricate subjects, license grants or quality scores. Asset provenance and visual review remain M0 dependencies.

M0 stays open until the provenance-indexed corpus, actual per-stage/resource baseline and quality review exist. M1 controller work can proceed independently using the known private asset and authored fixtures. It must leave broader generated-image quality untested. M3/M4 integration and tier acceptance retain their dependency gates.

### Next increments

1. M1 controller logic and collision tests, followed by viewer integration and actual-browser acceptance.
2. M0 corpus acquisition/provenance and frozen subject annotations; complete stage measurements using those assets.
3. M2 schema/storage/recovery increments in disposable fixtures, preserving legacy endpoints.
4. Mesh/anatomy feasibility before expanding rigs or claiming T1 acceptance.

## Milestone ledger

| Milestone | Status |
|---|---|
| M0 | Partial audit/source review and development baseline; full corpus and quality accounting pending |
| M1 | T0 known-canine scene and portable sample merged; combined CI passed at cd2f2e0 |
| M2 | Contracts, atomic store, artifact publication, coordinator, worker ownership, executor/recovery, local input/review API and browser workflow merged with successful combined CI; actual model/global GPU integration pending |
| M3 | Manual preparation/review foundation merged; isolated bounded proposal contract in validation; provider/routing evaluation pending |
| M4–M10 | Planned; dependency and acceptance gates remain applicable |

A later isolated development baseline at `c804742` completed the existing Idol → stereo mesh → UniRig path on a licensed canine render. The 855,576-triangle result fails the runtime mesh budget, and its generated 32-bone rig is correctly refused by the current fixed 34-bone walking profile. See [source provenance, timings, memory and visual limitations](character-baseline.md). This demonstrates the remaining preparation/mapping work; it does not establish a playable new image or complete M0.

## M1 controller foundation

A standalone pure JavaScript controller introduces a fixed 60 Hz simulation with bounded 250 ms catch-up, vector-normalized movement, acceleration/deceleration, bounded heading changes and swept axis-aligned obstacle collision. Its conservative square footprint uses the configured radius as half-width. It reports actual displacement speed so blocked movement can drive idle animation. Reset returns to an obstacle-free origin and clears accumulated simulation time.

This increment does not expose a playable scene yet. Node tests cover frame schedules, diagonal input, thin-wall blocking/sliding, blocked speed, stopping/reset, invalid input and obstacle validation. They are included in `npm test`, `make test` and frontend CI. Rendering, canine anatomy and GPU performance remain untested by these logic tests.

## M1 known-canine scene increment

The scene adds a separate play page linked from a completed reviewed canine walking result. It consumes only `Walk_inplace`, preserves the normal preview, assumes two-metre horizontal extent, normalizes to Y-up and uses controller-owned motion. Keyboard input is scoped to the canvas and clears on focus/visibility loss. Camera orbit/follow, ground/wall collision, reset and standing-hold/walk crossfades are implemented. Unsupported sources/profiles/clips fail explicitly.

Browser tests were added first and failed with the missing page, then passed after implementation. Tests also found and fixed a negative initial animation-frame delta. All 17 functional Chromium tests passed, together with existing automated checks. The private dense dog loaded and moved with preserved vertex colors; known anatomical/motion defects remain outside this controller increment. Default WSL WebGL used llvmpipe, so its timings do not establish hardware performance. RTX 3060 D3D12 is available through process-local Mesa driver selection; standing-scene hardware benchmarking passed at `50dd059` (clean tracked files): Chromium 158.0.8127.18, ANGLE D3D12 NVIDIA RTX 3060, viewport 1920×1080, canvas 1052×650, DPR 1, warmed 60-second run with 3,598 frame samples, median 16.7 ms and p95 16.8 ms, no page errors. Scripted movement also changed world position without errors. This receipt does not certify full-screen 1080p rendering or natural gait; a sustained moving benchmark is recorded separately. Standalone packaging and broader M1 lifecycle acceptance remain pending; do not mark M1 complete.

## M1 portable sample increment

Completed reviewed canine jobs can download a read-only ZIP containing the in-place GLB, sanitized schema-v1 manifest with SHA-256, reusable controller/viewer source, HTML, locked Three.js dependency, Node version and instructions. The API validates job identity, eligibility, size, symlinks and self-contained resources. The sample validates the manifest and hash before playback. Original uploads, logs, source-job identifiers and local paths are excluded. Redistribution rights are not asserted by this local export.

TDD: package tests first failed on the missing module, API tests failed on the missing route, and a corrupted-hash browser test failed before verification was added. Positive/rejection/storage-preservation tests now pass. All 18 browser tests passed, including ten explicit load/dispose cycles with removed canvases and lost WebGL contexts; hardware memory plateau is not established by that test.

Clean private export acceptance: 13,321,556-byte ZIP extracted into an isolated new directory, `npm ci --ignore-scripts` passed, static HTTP server only, desktop Chromium with RTX 3060 D3D12, movement and reset passed, no page errors, no authoring API or external network requests. Initial npm installation requires a cache or registry access. The exported source runs without inference services; it does not require a build step.

A sustained moving scene benchmark at `16960cb` passed with clean tracked files: 3,600 frames over 60 seconds, median 16.7 ms, p95 16.8 ms, viewport 1920×1080, canvas 1052×650, DPR 1, RTX 3060 D3D12, Chromium 158.0.8127.18. It does not establish full-screen 1080p performance or improved anatomy. The known canine remains an experimental generated asset with visible deformation limitations. T0 proves gameplay, not natural-motion quality or image-to-play acceptance.

M1 packaging integration and combined-commit CI are still required before completion. M0 corpus/quality baseline and M2–M10 remain open. Independent M2 schema/storage work can use the frozen M0 decisions while corpus-dependent model acceptance stays blocked.

## M2 contract foundation

The first M2 increment defines a private character schema, explicit stage states, safe relative artifact references, canonical input/parameter/tool-version fingerprints and immutable downstream invalidation. It separates predicted skeleton, semantic mapping and skinning: mapping-only changes invalidate motion/package while preserving skin and reconstruction; skeleton changes invalidate both mapping and skin. Changed body assessment preserves the splat/mesh and invalidates downstream mesh assessment/preparation.

Tests first failed on the missing module; additional unsafe encoded-path cases failed before path validation was tightened. The module rejects unknown schema/stages/fields, malformed successful records, unsafe paths, invalid hashes and nonfinite settings. Invalidation preserves the original record and old artifact references while removing successful status and execution fingerprint. Artifact paths use generated ASCII names; owner input filenames are not used as storage paths.

This is pure unexposed logic: no existing API, jobs, worker, GPU ownership or storage behavior changes. It does not establish durable publication, byte-verified cache reuse, restart recovery or resumed inference. Those require the following M2 storage/coordination increments and their own isolated fault/process/API/GPU acceptance. M1's sample and scene have merged; final combined CI is tracked separately before marking that milestone complete.

## M2 atomic metadata store increment

The opt-in store retains content-addressed revisions and atomically publishes a current pointer under a cross-process metadata lock. Compare-and-swap prevents stale writers from overwriting current state. Strict schema/content hash/path checks and streamed artifact verification reject corrupted, truncated, redirected and nonregular outputs. A post-rename directory-sync failure is explicitly uncertain and requires reconciliation, not a silent success or blind retry.

Eight isolated filesystem/process tests and all 95 Python tests pass locally. Previous revisions and orphaned publications are preserved. This increment is not connected to the app and does not implement artifact publication, GPU ownership, recovery or resume; those remain M2 work. See [storage details](character-storage.md).

M1 implementation reached main at `cd2f2e0`, with successful combined CI run `43031720372`. Contracts reached main at `434d7f2`; that revision's CI was cancelled. Full combined CI later passed with the contracts included at `7307cfd` (run `43041650418`). The local app was refreshed while idle, retains all existing outputs/models, and serves the play page and sample endpoint. Neither result completes the M0 corpus/model-quality baseline or later product tiers.

## M2 immutable artifact publication increment

Worker output copies now receive private unique attempt directories, streamed hashes, file/directory sync and atomic directory rename. Originals and previous/partial/orphaned attempts are preserved. Mutable worker outputs cannot alter an already copied snapshot. Publication leaves metadata unchanged; the coordinator must validate that snapshot and commit through revision CAS.

Thirteen new disposable publication tests first failed on the absent method and now pass; all 108 Python tests pass. Failures cover unsafe names/links/FIFO, changing sources, disk/sync errors and uncertain post-rename publication. No app, model, GPU or legacy persistence integration changes. M2 execution ownership/recovery/API integration remains pending.

The metadata store merged at `06a66af` and passed full combined CI `43042898464`. The CI infrastructure repair merged at `7307cfd` and passed combined CI `43041650418`; it uses the official digest-pinned Playwright image matching the locked package, retaining all actual browser acceptance tests.

## M2 coordinator transition increment

The coordinator claims stages using verified named dependencies and canonical input/settings/version fingerprints, returns only byte-verified cache hits, enforces one running stage per character, increments attempts and invalidates affected descendants. It validates immutable snapshots through explicit accept/review/reject decisions, persists hash-bound UTC receipts and commits with revision CAS. Late callbacks cannot replace corrections or retries. Original upload bytes must match the claimed hash.

Eighteen new transition tests and all126 Python/33 infrastructure tests pass locally. `CommitUncertain` propagates for reconciliation instead of being overwritten with a blind failure. No process, GPU or API integration is claimed. See [coordinator details](character-coordinator.md).

Artifact publication reached main at `11d24a0`, with successful combined CI `43046217270`. M0 corpus/model-quality baseline and M2 ownership/recovery/API work remain incomplete.

## M2 cooperating worker ownership increment

An unexposed Linux/WSL worker primitive durably records process identities before granting execution, holds an inherited resource lock, stops verified workers through pidfds and reconciles parent death conservatively. It refuses live-parent takeover and foreign/reused identities. Twelve disposable subprocess tests pass, including a red/green regression for Python startup hooks before grant and private log permissions. See [worker protocol and limits](worker-leases.md).

The coordinator reached main at `3db7849`, with successful combined CI `43049880465`. Existing model launchers, caches and API remain unchanged; model-specific adapters and actual inference/cancellation checks remain required. This ownership increment is not full M2 acceptance.

## M2 combined stage executor increment

The private executor connects stage claims, registered cooperating workers, successful exit/reaping, snapshot validation and CAS. It exclusively owns a character namespace, rejects conflicting services, reconciles restart including the claim-before-lease boundary, preserves timeouts and cache hits, and records cancellation only after termination. Sixteen real subprocess tests pass, including concurrent wait/cancel and uncertain completion. See [execution protocol](character-executor.md). API and actual model adapters remain unconnected; this is not full M2 acceptance.

Worker ownership reached main at `bc23fa8` with successful full combined CI `43055989345`. An evidence audit corrected earlier Dependency Graph run identifiers: publication CI is `43046217270`, coordinator CI is `43049880465`, sample CI is `43031720372`. The cancelled original contract CI is explicitly distinguished from later successful combined validation.

## M2 API and M3 manual foundation increment

An opt-in private character API now exposes real local CPU image preparation and manual anatomy review through the durable executor. Explicit upload identity supports duplicate reconnect, immutable originals, review/crop correction, status, selected verified artifacts, cancellation and retry. Prepared previews strip metadata; originals remain available even after cancellation. Context-aware validation is bound to the original claimed settings. The feature remains disabled by default, and no inference/reasoning provider or model adapter is registered. See [API behavior and limits](character-api.md).

The combined executor reached main at `75e784c` with successful full combined CI `43071135069`. API/browser model integration and corpus acceptance remain incomplete; this input/manual foundation is not full M2/M3 acceptance.

## M2/M3 browser review and reconnection increment

A separate character page connects the opt-in API to real image/manual-review controls, saved-character selection, crop confirmation, status, cancellation/retry and verified downloads. Validated URL identity reconnects after refresh without submitting work. Delayed reports wait before enabling edits; delayed status cannot regress newer displayed revisions. Local preview URLs are disposed and the page uses local assets/API only. See [workflow behavior and validation limits](character-workflow.md).

The API reached main at `e5b720a` with successful full combined CI `43075985489`. The browser workflow is a preparation/review foundation; model adapters, reasoning evaluation and corpus/quality gates remain unaccepted. 3D/playable stages are explicitly unavailable in this new workflow.

The browser workflow subsequently reached main at `e6ab907` with successful combined CI `43081279947`, including isolated real-API browser acceptance and read-only compatibility checks of the owner's saved canine.

## M3 bounded proposal contract

An isolated [reasoning contract](anatomy-reasoning.md) adds metadata-stripped image views, closed typed proposals, supplied-view evidence checks, explicit manual fallback and call/byte/deadline limits. Every proposal requires review. Timeout/caller cancellation retains an active-call guard until completion; bounded close reports unfinished cancellation. No provider, external request, API/UI integration or automatic anatomical acceptance is enabled. Fake-provider and image/parser tests validate the boundary; actual routing accuracy and provider cost remain untested.
