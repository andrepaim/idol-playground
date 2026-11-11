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

The existing owner dog and generated derivatives may be used for local regression; no redistribution rights are inferred. Public CI must use authored procedural fixtures with documented provenance. The 18 land images, nine swimmer images and annotated held-out split are not yet assembled. Do not fabricate subjects, license grants or quality scores. Asset provenance and visual review remain M0 dependencies.

M0 stays open until the provenance-indexed corpus, actual per-stage/resource baseline and quality review exist. M1 controller work can proceed independently using the known private asset and authored fixtures. It must leave broader generated-image quality untested. M3/M4 integration and tier acceptance retain their dependency gates.

### Next increments

1. M1 controller logic and collision tests, followed by viewer integration and actual-browser acceptance.
2. M0 corpus acquisition/provenance and frozen subject annotations; complete stage measurements using those assets.
3. M2 schema/storage/recovery increments in disposable fixtures, preserving legacy endpoints.
4. Mesh/anatomy feasibility before expanding rigs or claiming T1 acceptance.

## Milestone ledger

| Milestone | Status |
|---|---|
| M0 | Partial audit/decisions; corpus and full baseline pending |
| M1 | Controller merged with successful combined CI; play scene and portable sample in progress |
| M2–M10 | Planned; dependency and acceptance gates remain applicable |

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
