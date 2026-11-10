# Textured mesh generation

Choose **Textured mesh · .glb** in the app to reconstruct a polygon mesh directly from the uploaded photo. This uses TripoSR and produces a different reconstruction from Idol's Gaussian splat. The exported mesh has UV coordinates and an embedded color texture; optional [experimental automatic rigging](automatic-rigging.md) follows mesh inspection.

## Setup and use

The accepted platform is Linux/WSL on x86-64 with an NVIDIA GPU. The isolated mesh environment uses Python 3.11 and PyTorch 2.5.1/CUDA 12.4. It does not change Idol's Python environment.

From an existing Idol installation:

```sh
make setup-mesh mesh-models
npm run build
./run.sh
```

For a mesh-only installation:

```sh
make bootstrap setup-mesh mesh-models
./run.sh
```

The launcher prefers `.venv` when present and falls back to `.venv-check`, so the API can serve mesh generation without installing Idol. The separate `.venv-triposr` process performs reconstruction. `make setup-mesh` checks required imports, offscreen rendering, and surface/export regressions. `make mesh-models` downloads the pinned public assets; no Hugging Face login is required. First generation can download missing assets once the environment is installed.

Texture baking needs an OpenGL 3.3 implementation with EGL, normally supplied by Mesa on Linux/WSL. Software EGL is supported; CUDA handles neural reconstruction and texture queries. Triangle extraction uses CPU PyMCubes, avoiding a requirement for a system CUDA compiler. If environment checks fail, resolve the reported EGL/CUDA/library gap before inference.

Select a clear subject. For characters, a full-body image with separated limbs gives reconstruction and later rigging a better starting point. Existing transparency is respected; opaque photos use the pinned U2Net background remover. Inspect the prepared image when segmentation removes or retains unwanted parts.

## Controls and outputs

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
