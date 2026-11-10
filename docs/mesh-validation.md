# Local mesh validation

Runtime candidate: `9ff7b52` (same inference code as initial `c315eb0`; the amendment only reworded planning prose). Hardware: NVIDIA GeForce RTX 3060, 12 GB, driver 610.88. Idol used its existing PyTorch 2.15 CUDA 13.2 environment; TripoSR used the locked PyTorch 2.5.1 CUDA 12.4 profile. Date: 2026-11-10.

## Actual inference and browser acceptance

Real uploads through the application, without mocked generation, produced self-contained textured GLBs at grid 192, 25,000 triangle cap, 1024px texture, seed 42. One owner-provided quadruped and two public full-body humanoid TripoSR examples completed. Their worker times were 14.0s, 9.9s and 9.6s; API completion times were 18.1s, 13.3s and 12.8s. Each reported 1938 MiB peak PyTorch allocation. These values exclude other applications and are observations, not guaranteed ETAs.

GLB geometry, indices, finite positions/UVs and embedded textures passed validation and reload. The actual browser preview, wireframe, reset and GLB download worked without JavaScript page errors. Cancelling a real mesh job released its worker and permitted subsequent jobs. Inputs, exports, screenshots and raw receipts stay in ignored local storage.

The same server completed Idol → mesh → Idol using a public horse image, seed 42; each Idol run used synthetic mode, 10 steps and 65,536 Gaussians. Valid PLY, GLB and PLY downloads completed in 79.6s (initial cold run), 14.3s and 34.0s. Status showed cached Idol loaded, released, then reloaded. Whole-GPU memory after those jobs was approximately 6798, 3101 and 6797 MiB; this includes desktop/driver usage and is not per-model memory. The mesh child exited before the next job. An early polling client hit a transient keepalive reset during cold loading; reconnecting recovered the still-running job, which completed successfully.

## Automated checks

- 33 API/logic tests, including independent readiness, validated settings, busy-job rejection, cancellation/reaping, timeout/error propagation, persistence, export validation, cache release and timing.
- 30 infrastructure tests, including local/CPU launcher selection.
- 5 Chromium browser acceptance tests for both output modes, failure/retry, mesh controls, cancellation and renderer disposal. Browser rendering used software WebGL.
- 3 isolated backend regressions for scalar-field axis order, empty geometry and smooth normals across UV seams after GLB round trip.
- Ruff, ESLint, documentation/link checks, repository data guard and full-history secret scanning passed.

## Quality limits and next step

Visual inspection confirms recognizable prototype geometry. The sitting quadruped has incomplete anatomy and two disconnected components. Humanoid examples have two to seven components; only one tested simplified mesh is watertight. Automatic simplification does not create animation topology or recover hidden limbs. A bust was excluded from full-body acceptance.

Static mesh acceptance does not establish usable skinning, anatomical bone placement, deformation quality or game-engine compatibility. Parent issue #2 remains open. Next: run the learned skeleton and skinning models sequentially on full-body humanoid and quadruped candidates, retain textures, validate joints/weights and inspect an actual deformation before exposing a rigged export.
