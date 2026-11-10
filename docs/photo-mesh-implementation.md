# Photo-to-mesh implementation

Status: static mesh increment implemented and validated locally; PR #17 awaits CI and merge. See [validation evidence](mesh-validation.md). Parent: issue #2. The existing Game Character plan remains the longer-term rigging/export roadmap.

## Behavior and acceptance

Add an output choice for the existing uploaded photo: Idol Gaussian splat or TripoSR textured polygon mesh. Mesh generation runs locally, reports its real stages and calibrated ETA, exports a self-contained textured GLB, and opens a mesh viewer with orbit, wireframe, and download. Preserve the existing splat API/defaults and saved outputs.

Feasibility includes Paçoca as a quadruped and suitable public reconstruction examples. Check actual GPU memory, generated anatomy, topology/UV/material integrity, and export round trips. TripoSR is a baseline to evaluate, not a preselected quality winner. If limb separation/anatomy is unsuitable, record the failure and evaluate improvements before automatic rigging. Do not label an unrigged mesh animation-ready.

## Components and steps

1. Pin a separate TripoSR source/environment and public model/encoder/background-removal assets; verify local setup and offline operation.
2. Run real reconstruction, preserve the source mesh, remove degenerate geometry, simplify before UV generation, bake appearance from the inferred field, and export GLB with embedded textures.
3. Add a bounded subprocess adapter and shared GPU ownership. Release Idol tensors before starting TripoSR, and terminate/reap the mesh process on failure/cancellation. Initially retain Idol's existing in-process cache; require actual switching evidence before accepting this smaller change instead of prematurely rewriting both backends.
4. Extend readiness/job metadata and validated settings without breaking existing clients. Keep failed jobs actionable and completed metadata readable after restart.
5. Add mesh controls/viewer, real stage reporting, download, wireframe and reset; dispose previous renderer/resources before loading another result.
6. Apply meaningful failure/export/API tests, browser acceptance for both outputs, real RTX 3060 runs and Idol → mesh → Idol switching. Complete current-main integration, merged PR, and combined-main CI.
7. Inspect mesh quality before the next rigging increment. Expand quadruped acceptance and revise the parent roadmap with measured findings; an initial mesh increment does not close the parent's full rigging acceptance.

## Risk and evidence

GPU/toolchain/model loading changes require exact-revision real hardware evidence. CPU substitutes only validate orchestration. Test busy-job rejection and missing setup. Cover process failures, child-process cleanup, damaged GLB files, setting bounds, and compatibility with saved jobs. Mesh export must include usable triangles, UVs, embedded appearance and finite geometry after round trip. Browser checks cover mode changes, progress, failures/retry and viewer disposal.

Keep user inputs/results, raw benchmark renders, downloaded source/checkpoints and extra environments ignored. Public benchmark summaries use sanitized settings/statistics, not owner images or job paths. Wait for active user jobs before any restart. No releases, paid services, production deployment or source-license changes are included.
