# Splat-derived mesh integration validation

Acceptance target: Linux/WSL, NVIDIA RTX 3060 12 GB, driver 610.88. Idol uses its existing locked environment; stereo uses isolated Python 3.11, PyTorch 2.5.1/CUDA 12.4, DLNR and Open3D. Capture uses headless Chromium with software WebGL. No input images, generated artifacts or private job identifiers are published here.

The integrated implementation reuses the approved camera, stereo, fusion and linear-color export math. Defaults are 36 pairs, 512px, 0.002 voxel and largest component. See [experiment measurements](splat-mesh-results.md), [integration plan](splat-mesh-integration.md) and [current usage](mesh-generation.md).

Automated acceptance covers upload/source routing, independent readiness, preserved sources, exclusive ownership, phase failures, cancellation, model checksums, vertex-color validation, saved results and browser controls. Existing texture-based generation and rigging checks remain in the suite. A native capture cancellation audit stopped all seven observed Chromium/driver descendants and reaped the worker before returning ownership. A Blender/FBX color-attribute probe also retained the source colors.

## Integrated conversion

The actual saved-splat UI path completed on implementation revision `68c3f88`: 358.4 seconds total, including 323.26 seconds software view capture; DLNR reported 590 MiB peak PyTorch allocation. Output retained 314,023 vertices / 627,159 triangles, vertex colors, Y-up orientation and the expected non-watertight status. The source splat SHA-256 remained unchanged and no Idol phase ran. GLB download, source download availability, wireframe/reset, warnings, saved-result reopening and rig-button readiness passed without browser page errors.

Evaluation against the original eight withheld cameras reproduced mean silhouette IoU **95.777%**, minimum **94.359%**, matching the approved experiment. The integrated mesh was visually inspected in the app. Actual capture cancellation/retry and HTTP 409 while busy passed. These checks establish fidelity for this saved subject, not general quality. CPU/browser fixtures cannot establish reconstruction quality or CUDA performance. Broader subject coverage, production topology, engine materials/retargeting and authored animation remain outside this integration.


## Full learned rigging

The new 627,159-triangle mesh completed UniRig skeleton prediction, skin-weight prediction, source-mesh transfer, diagnostic bend and export in 153.2 seconds. The result has 34 bones and all 314,023 vertices. Skeleton/skin models reported 3,999 / 4,216 MiB peak PyTorch allocation. The diagnostic rotation moved 179,881 vertices with maximum displacement 0.1055 in model units.

Independent reimport of GLB, FBX and Blender retained 34 bones, valid binding and the vertex-color attribute, with identical measured linear mean RGB across all three. The app's neutral preview retained the source appearance; skeleton and bend controls were inspected. FBX material use in a game engine was not validated and may require explicitly reading the color attribute. A successful diagnostic bend does not establish correct anatomical rigging or useful game animation.


## Fresh upload and setup

The real UI completed the default photo upload → Idol → views → stereo → surface → GLB sequence in **485.0 seconds**, including 133.95 seconds sampling and 308.53 seconds capture. Settings were real photograph, 50 steps, 262,144 Gaussians, guidance/time shift 3 and seed 42, fine surface and largest component. All 50 sampling steps were recorded. The generated source splat was byte-identical to the approved saved reference. Output contained 313,950 vertices / 627,016 triangles with valid vertex colors; small reconstruction differences remain possible. The UI showed the final colored mesh and source download without page errors. Cancelling a separate real Idol child during image analysis stopped it, released the slot and permitted the successful retry.

A clean pinned GS2Mesh source checkout plus the verified cached checkpoint passed setup at revision `02f2a66`; a disposable real-Git regression first reproduced and then prevented a fresh-clone checkout-state failure. The same regression confirms later local source edits are refused and preserved. Full local checks on that revision passed 51 API/logic tests, 30 infrastructure tests, nine Chromium fixture scenarios, lint, docs, build and committed-history security. Three native TripoSR regressions also passed.

Inference/geometry acceptance above ran on `68c3f88`; subsequent changes affect setup, recent-result limit, progress wording and documentation. Runtime candidate `d6393e4` is used for the final model-switching and persisted-result acceptance. Private raw receipts retain tested revision, settings and per-stage measurements.
