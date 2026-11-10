# Splat-derived mesh integration

Authorized after owner review of the successful fidelity experiment. Integrate the approved reconstruction path into ordinary generation and completed-splat conversion; preserve the original shape, artifacts and older workflows.

## Behavior and acceptance

Default the UI's mesh method to Idol-derived reconstruction. Uploading in that mode generates an Idol splat in a cancellable isolated process, captures calibrated stereo views, predicts depth and fuses/export the approved upright vertex-colored mesh. A recent-results picker reopens persisted completed jobs; a completed splat also offers Create mesh, skipping Idol inference and preserving the source job. Keep TripoSR as an explicit legacy method; preserve old API defaults and existing saved jobs.

Use the accepted 36-view geometry, 512px images, 42-degree field of view, 0.075 baseline and 0.002 voxel by default. Offer a coarser 0.004 setting and explicit largest/all component selection. Retain raw/source artifacts; make removal of detached pieces clear. No automatic decimation that changes the approved geometry.

Separate readiness/setup for the stereo environment and pinned source/weights. GPU stages share the app's one-job slot. Every phase is a bounded process group with cancellation/reaping; cache release precedes the work and no slot is freed while a worker remains alive. Capture runs headless/offscreen without relying on the app's active-job status or a hard-coded local server. Persist completion/failure/cancellation and source references. Progress reports actual render/stereo counts and learned stage ETA.

Preview and download the vertex-color GLB honestly. Extend existing export/rigging validation to preserve either embedded textures or vertex colors; check the complete learned skeleton/skinning/export path on a new mesh. Preserve all earlier texture-based workflows. State dense geometry, holes and experimental rigging limits.

## Steps and checks

1. Claim the integration issue, isolate its worktree, record this plan. Add meaningful failing tests for source validation, readiness/routing, cancellation, appearance integrity and progress.
2. Add isolated setup/assets and a thin phase worker reusing the proven experiment math. Add deterministic progress hooks, callable functions and export integrity checks without altering the accepted camera geometry.
3. Add job orchestration for upload and source-splat conversion, validated settings, persistent metadata, independent readiness and exclusive ownership.
4. Update output/method controls, source conversion, stage progress/ETA, warnings and downloads. Adapt vertex-color rigging where needed.
5. Run automated/API/browser/export checks. Run actual RTX 3060 upload → mesh, existing-splat conversion, cancellation/retry, switching and rigging. Compare the approved source against held-out cameras before claiming fidelity. Preserve owner media and active jobs; restart only idle servers.
6. Integrate current main, review the combined diff, merge PR and verify combined-main CI. Update docs/status. No release or owner-asset publication.

## Risks and boundaries

CUDA/process/model ownership, browser-child cleanup, source preservation, calibration, color-space/export correctness and Blender behavior require actual checks. CPU mocks do not establish GPU behavior or fidelity. Keep the legacy PLY API/default and saved texture meshes compatible. New UI method selection is explicit in requests. Timings must include capture, which was the experiment's main bottleneck; do not display stereo-only time as total ETA.

This integrates the reviewed prototype, not a guarantee of game-ready geometry or general multi-object fidelity. Largest-component cleanup may omit accessories. Vertex colors differ from a UV texture map; verify each supported export rather than claiming texture compatibility. Capture acceleration, authored animation/retargeting and game-engine acceptance remain separate work.
