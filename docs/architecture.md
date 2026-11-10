# Current architecture

The app is a loopback FastAPI server with a Vite-built browser interface. `app.py` validates PNG/JPEG/WebP uploads and runs one generation at a time in a single-worker thread executor. A second generation receives HTTP 409.

Idol loads lazily and stays in GPU memory after completion. `model_setup.py` downloads pinned public checkpoints and encoders into ignored `models/`. `progress.py` temporarily instruments the SDK for stage timing and completed-step counting; the sampler itself is unchanged.

The browser polls `/api/jobs/{id}`, displays stages and adaptive ETA, loads the final PLY with GaussianSplats3D, and offers download. Three.js renderer ownership and disposal support repeated generations.

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | SDK, model, and active-job state |
| `POST /api/generate` | Validated multipart upload and generation settings |
| `GET /api/jobs/{id}` | Progress or persisted completed job metadata |
| `/outputs/...` | Locally stored artifacts |

Jobs store input, PLY, prepared image, camera, settings, and completed metadata under UUID output folders. Active jobs exist in memory; an interrupted run cannot currently resume. Timing calibration is stored in `outputs/.timings.json`.

The server has no authentication and binds to `127.0.0.1`. It is intended for personal local use. Public GitHub source does not publish the app or its artifacts.

Separate model-worker processes, cancellation, textured meshes, skeletons, skinning, and GLB/FBX exports are proposed in the [Game Character plan](game-character-plan.md), not current capabilities.
