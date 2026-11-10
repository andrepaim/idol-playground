# Current architecture

The app is a loopback FastAPI server with a Vite-built browser interface. `app.py` validates PNG/JPEG/WebP uploads and runs one generation at a time in a single-worker thread executor. A second generation receives HTTP 409.

Idol loads lazily and stays in GPU memory after splat completion. Mesh jobs release cached Idol tensors. The preferred mesh method runs Idol in an isolated child when uploading, then sequential capture, DLNR stereo, TSDF fusion and export processes. Saved-splat conversion skips Idol inference. TripoSR remains a separate legacy subprocess. `model_setup.py` downloads pinned public checkpoints and encoders into ignored `models/`. `progress.py` temporarily instruments the SDK for stage timing and completed-step counting; the sampler itself is unchanged.

Mesh output is selected with `output_type=mesh` on the generation endpoint; omitting it preserves splat behavior. The UI sends `mesh_backend=idol`; omitted mesh method remains `triposr` for API compatibility. Readiness is separate under `splat_mesh`, `mesh` (legacy) and `rig`. The mesh adapter validates a self-contained vertex-colored or textured GLB, and the mesh viewer disposes its controls, geometry, textures, and renderer before replacement. `POST /api/jobs/{id}/cancel` requests mesh cancellation; ownership remains held until the worker is reaped.

The browser polls `/api/jobs/{id}`, displays stages and adaptive ETA, loads the final PLY with GaussianSplats3D, and offers download. `web/turntable.js` records a full orbit of the current preview (splat or mesh) from its canvas with `MediaRecorder`, entirely in the browser. Three.js renderer ownership and disposal support repeated generations.

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | SDK, model, and active-job state |
| `POST /api/generate` | Validated multipart upload and generation settings |
| `GET /api/jobs` | Recent completed result summaries |
| `POST /api/jobs/{id}/mesh` | Convert completed splat without regeneration |
| `POST /api/jobs/{id}/rig` | Rig completed mesh |
| `POST /api/jobs/{id}/cancel` | Cancel mesh/rig work and reap workers |
| `GET /api/jobs/{id}` | Progress or persisted completed job metadata |
| `/outputs/...` | Locally stored artifacts |

Jobs store input, PLY, prepared image, camera, settings, and completed metadata under UUID output folders. Active jobs exist in memory; an interrupted run cannot currently resume. Timing calibration is stored in `outputs/.timings.json`.

The server has no authentication and binds to `127.0.0.1`. It is intended for personal local use. Public GitHub source does not publish the app or its artifacts.

Splat-derived meshes, legacy TripoSR, cancellation, mesh preview, skeleton prediction, skinning and GLB/FBX/Blender export are implemented. Normal splat generation still uses its existing in-process cache. Game topology, engine acceptance and authored animation remain [Game Character work](game-character-plan.md).

Optional automatic rigging uses a third pinned environment and sequential bounded UniRig/Blender phase processes. Both skeleton and skin models run locally with offline assets; exports retain source UVs/textures or vertex colors and are reimported for binding/appearance checks. A separate rig job preserves its completed static source job and shares GPU ownership, cancellation and persisted status with mesh generation.

Turntable recording on a walking result holds the current animation pose and locks preview controls during capture. Afterwards it restores the prior playback state, keeping forward root travel and camera follow from moving the orbit target while recording.
