# Polygon mesh generation

Choose **3D mesh · .glb** and **From Idol splat · preferred**. The app generates an Idol Gaussian splat, renders calibrated stereo pairs, predicts depth with DLNR and fuses the surface with Open3D. It exports a vertex-colored GLB derived from the splat rather than a second independent reconstruction of the photo.

## Setup and use

Linux/WSL x86-64 with NVIDIA CUDA is the accepted platform. From an existing Idol installation:

```sh
make setup-splat-mesh splat-mesh-models
npm run build
./run.sh
```

Uploading in this mode also needs `make setup-local models`. Converting a saved splat only needs the stereo environment/assets and the built frontend. The launcher can serve from `.venv-check` if Idol's `.venv` is absent. `make setup-splat-mesh` installs locked Python 3.11, PyTorch 2.5.1/CUDA 12.4, Open3D and Playwright in `.venv-stereo`, installs Chromium, and checks CUDA imports and headless rendering. Minimal systems may need Playwright's system libraries. The setup is independent of TripoSR and UniRig.

`make splat-mesh-models` pins GS2Mesh source to `560f3e8a2349aaad24fe9444ef1ca2770aeec5ab` and downloads its public DLNR Middlebury checkpoint, verifying SHA-256 `57e46b8fed66b685f732b730ebffd71998dcabea49f8443ca77e015419f6ae18`. Assets remain in ignored `models/splat-mesh`. Complete setup before requesting a job. Workers load local assets with offline model settings; capture serves all resources locally without relying on a running app endpoint.

Upload a clear image, or reopen a completed splat with **Saved results** and click **Create mesh from this splat**. Conversion skips Idol inference and creates a separate job; it never replaces the original splat. The picker includes up to 50 completed results with existing artifacts. Older persisted splat jobs remain supported.

## Splat-derived settings and outputs

| Setting | Values | Default |
|---|---|---|
| Surface quality | Fine / Balanced | Fine: 0.002 voxel; Balanced: 0.004 |
| Components | Largest / All | Largest |
| Idol settings on upload | Same as normal splat generation | 50 steps, 262,144 Gaussians, seed 42 |

Capture uses 36 stereo pairs, 512px images, 42° field of view, radius 1.5 and baseline 0.075. Largest-component cleanup can remove detached accessories as well as noise; select All to retain disconnected parts. There is no automatic triangle reduction that changes the approved reconstruction.

Progress reports Idol stages when uploading, actual image and stereo-pair counts, surface fusion and export. ETA includes capture and learns successful timings in `outputs/.splat-mesh-timings.json`. Software WebGL capture is the main bottleneck and can take several minutes; CUDA stereo time alone is not the total duration. Preview loading time is separate.

Jobs retain `object.glb`, `source.ply`, `raw-mesh.ply`, `mesh.json`, settings, prepared image where available, per-phase logs and working captures/depth. Raw PLY retains the colored surface in source-splat coordinates before component cleanup; intermediate fusion data remains in subfolders. `source.ply` preserves the input Gaussians. Completed, failed and cancelled job metadata persists; interrupted work cannot resume.

The viewer supports orbit, zoom, wireframe, reset, warnings and downloads. The GLB uses linear vertex colors and an unlit material, without a UV texture map. It is marked unrigged. [Experimental automatic rigging](automatic-rigging.md) preserves vertex colors through GLB, FBX and Blender exports; FBX consumers may need a material that reads the color attribute.

## Lifecycle and API compatibility

Splat, both mesh methods and rigging share one exclusive slot. Cached Idol tensors are released before mesh/rig workers start. Image-to-mesh Idol inference runs in a cancellable child process; capture, stereo, fusion and export each have bounded workers. Cancellation retains ownership until the worker and its browser descendants stop. The next normal splat request reloads Idol.

`GET /api/status` reports `splat_mesh.ready`, `weights_downloaded` and `upload_ready` independently of legacy `mesh` and `rig`. `POST /api/jobs/{id}/mesh` converts a completed splat, accepting `surface_quality=fine|balanced` and `component_mode=largest|all`. `GET /api/jobs` lists completed result summaries. On `POST /api/generate`, the UI sends `output_type=mesh&mesh_backend=idol`; omitted `output_type` remains splat, and the API's omitted mesh method remains `triposr` for existing clients. Cancellation uses `POST /api/jobs/{id}/cancel`.

## Fidelity and limitations

The accepted dog experiment measured 95.78% mean silhouette agreement over eight held-out cameras. This measures fidelity to that splat's outline, not real anatomy, unseen-surface accuracy, general reconstruction quality or deformation topology. See [experiment results](splat-mesh-results.md) and [integrated validation](splat-mesh-integration-validation.md).

Fine output can exceed 600,000 triangles. Holes, rough details and soft/thin surfaces remain possible. The result is not guaranteed watertight or game-ready. Automatic rigging does not repair anatomy or create clean game topology. Capture acceleration, topology refinement, UV baking, engine import and authored animations remain separate work.

The API validates finite positions, triangle indices, bounds and either valid vertex colors or embedded UV textures. Browser/API tests cover routing, readiness, persistence, cancellation, progress and viewer lifecycle; actual GPU and fidelity acceptance are additionally required for reconstruction changes.

## Legacy TripoSR method

Install with `make setup-mesh mesh-models`, then select the explicit legacy method. This uses a separate `.venv-triposr` and directly predicts a different shape from the photo. It exports UVs and an embedded texture. Software EGL/OpenGL 3.3 is needed for baking. The method remains available for older workflows; it did not meet the owner's shape-fidelity requirement for the tested dog.

## Legacy TripoSR settings and outputs

| Setting | Supported values | Default |
|---|---|---|
| Triangle budget | 10,000 / 25,000 / 50,000 / 100,000 | 25,000 |
| Texture size | 512 / 1024 / 2048 px | 1024 |
| Surface grid | 128 / 192 / 256 | 192 |
| Seed | 0–2,147,483,647 | 42 |

The budget caps simplification; a source mesh below that budget keeps its actual smaller triangle count. The viewer displays actual exported statistics, supports orbit/zoom, wireframe, and reset, and downloads the self-contained GLB.

Stages report background preparation, model loading, reconstruction, surface extraction, simplification, texture baking, and export. Known field/texture samples provide real progress; opaque operations remain indeterminate. ETA starts approximately and learns timings by resolution/budget in `outputs/.mesh-timings.json`. A cancelled or failed job does not calibrate successful timings.

Only one generation runs at a time. Starting a mesh job releases cached Idol tensors before launching the mesh process. The mesh process exits after completion, cancellation, or failure; the next splat generation reloads Idol. Cancellation is currently available for mesh jobs. On server shutdown, mesh workers are stopped and reaped.

Each job retains `object.glb`, `prepared.png`, `texture.png`, `source-mesh.glb`, `mesh.json`, settings, and `job.json` where available. The source mesh preserves the original reconstruction before simplification. The local `worker.log` is for diagnostics. Inputs, outputs, and logs stay ignored. Completed/failed/cancelled mesh metadata remains readable after restart; interrupted generation cannot resume automatically.

## Validation and quality boundaries

The adapter cleans degenerate/duplicate faces, simplifies before UV unwrapping, bakes color from the inferred field, preserves smooth normals across UV splits, and converts Z-up source coordinates to glTF Y-up. Export is round-tripped and the API independently checks GLB bounds, triangle indices, finite positions/UVs, embedded PNG/JPEG textures, and material references.

Valid export does not prove correct anatomy, clean deformation topology, or suitability for animation. Single-image results can have fused limbs, disconnected fragments, holes, and inferred appearance on unseen surfaces. Paçoca's sitting photograph is a challenging quadruped input; inspection is required before rigging. A static GLB is explicitly marked unrigged.

Initial real RTX 3060 trials exported Paçoca, horse, robot, a bust, a cartoon figure, and a full-body humanoid. Mesh worker stages were approximately 10–16 seconds at 192/256 grids with 25,000-triangle budgets and 1024 textures, using approximately 1.9–2.4 GiB peak PyTorch allocation. Whole requests also include worker startup and validation. These are prototype measurements, not a general speed or quality guarantee; final revision/scenarios are recorded in the implementation PR.

```sh
make test
make test-browser
make test-mesh-backend
```

CPU/API tests exercise missing setup, settings, exclusive-job handling, cache release, process errors/timeouts/cancellation/reaping, export validation, ETA learning, and persistence. Browser fixtures validate both viewer lifecycles and controls; they do not establish CUDA performance or reconstruction quality. Actual GPU acceptance must additionally check real exports, cancellation, and Idol → mesh → Idol switching. See [validation](validation.md) and the [implementation plan](photo-mesh-implementation.md).

## Pinned sources

| Component | Source | Revision |
|---|---|---|
| TripoSR code | VAST-AI-Research/TripoSR | `107cefdc244c39106fa830359024f6a2f1c78871` |
| Reconstruction weights | stabilityai/TripoSR | `5b521936b01fbe1890f6f9baed0254ab6351c04a` |
| DINO configuration only | facebook/dino-vitb16 | `f205d5d8e640a89a2b8ef0369670dfc37cc07fc2` |
| U2Net | rembg release v0.0.0 | Published MD5 `60024c5c889badc19c04ad937298a77b` |

The DINO encoder weights are included in the reconstruction checkpoint; no second encoder-weight download is needed. The backend loads local assets with Hugging Face offline mode, and initializes the checkpoint with `weights_only=True`. Third-party source/license material remains alongside the ignored downloads. See [notices](../THIRD_PARTY_NOTICES.md).

See [local validation evidence](mesh-validation.md) for tested settings, hardware observations and quality limits.
