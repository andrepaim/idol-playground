# Idol Playground

Turn a single image into a 3D Gaussian splat or polygon mesh in a local web app. Preview results in the browser, download a turntable video, or use the experimental tools to rig a mesh and animate a supported canine rig. Splat generation uses [Idol](https://huggingface.co/speridlabs/idol).

## See it in action

Paçoca, reconstructed from one photograph and rotated in the app.

[![Paçoca’s photograph alongside a rotating 3D Gaussian splat in Idol Playground](docs/demos/pacoca-turntable.gif)](docs/demos/pacoca-turntable.mp4?raw=1)

[Download the MP4](docs/demos/pacoca-turntable.mp4?raw=1) · [Demo details](docs/demos/README.md)

## Run locally

| Workflow | Supported setup |
| --- | --- |
| Gaussian splats | Linux or WSL with NVIDIA CUDA, or macOS on Apple Silicon with PyTorch MPS |
| Polygon meshes and automatic rigging | Linux or WSL on x86-64 with NVIDIA CUDA |
| Canine walking | The Blender environment installed by `make setup-rig`, plus a completed supported rig |

Install Git, [uv](https://docs.astral.sh/uv/) 0.12.3, Python 3.11 and Node.js 22. The project pins its development Node version in [`.node-version`](.node-version). Optional backend setup and development commands also use Make. The preview requires WebGL2.

```bash
git clone https://github.com/andrepaim/idol-playground.git
cd idol-playground
uv sync --locked --extra local
npm ci
npm run build
uv run --no-sync python model_setup.py
./run.sh
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Use `PORT=8002 ./run.sh` to select a different port. The server binds to loopback for personal use.

The initial splat model download is about 5 GB and uses public assets without a Hugging Face login. You can skip `model_setup.py` and let the first generation download missing files. Subsequent inference loads the cached files locally.

PyTorch must detect CUDA or MPS for splat generation. `make doctor` reports the accelerator and model setup. If you hit a memory limit, close other GPU applications and reduce the Gaussian count. Idol’s model card reports about 7.2 GB of peak VRAM for a full request. Available memory and usage depend on your hardware and settings. [Idol model card](https://huggingface.co/speridlabs/idol)

Idol stays loaded between splat jobs. Starting a mesh, rig or walk job releases the cached model, so the next splat job reloads it. CUDA splat sampling runs without compilation by default. Set `IDOL_OPTIMIZE=1 ./run.sh` to try the SDK's optimized CUDA path. Apple Silicon uses eager sampling. [Getting started](docs/getting-started.md) · [Apple Silicon validation](docs/validation.md#apple-silicon-splats)

## Generate and preview a splat

Upload a PNG, JPEG or WebP up to 20 MiB and 25 megapixels. The app corrects EXIF orientation and scales the longest side to at most 2,048 pixels. Choose **Real photograph** or **Render / AI-generated image**, select **3D splat · .ply**, and generate. A clear image of one object works best.

The defaults are 50 steps, 262,144 Gaussians, guidance 3, time shift 3 and seed 42. For a quick first run, try 10 steps and 65,536 Gaussians. Progress shows stages, completed sampling steps and an adaptive ETA. The estimate excludes initial model download and browser preview loading.

Drag to orbit, scroll to zoom and right-drag to pan. Download the `.ply` to use the splat in a compatible viewer. The download remains available if the preview fails.

## Create a polygon mesh

```sh
make setup-splat-mesh splat-mesh-models
```

Choose **3D mesh · .glb** and **From Idol splat · preferred** to reconstruct a surface from the generated splat. To skip Idol inference, reopen a completed splat and select **Create mesh from this splat**. Conversion creates a separate job and exports a vertex-colored `.glb` using calibrated stereo views, DLNR depth estimation and surface fusion.

For a UV-textured `.glb` reconstructed directly from the photo, install `make setup-mesh mesh-models` and select **TripoSR · legacy**. Inspect either mesh for holes, fused limbs and other reconstruction errors before rigging. The splat-derived method can produce dense geometry, and view capture can take several minutes with software WebGL. [Mesh setup, settings and limitations](docs/mesh-generation.md)

## Rig and animate a character

```sh
make setup-rig rig-models
```

Open a completed mesh and select **Auto rig · experimental** to add a skeleton and skin weights with UniRig. Use **Skeleton** and **Test bend** to inspect the result. The rig is saved separately and includes GLB, FBX and editable Blender exports. [Automatic rigging](docs/automatic-rigging.md)

For a rig that matches the supported 34-bone canine hierarchy, review the paw assignments, choose a gait and travel mode, then select **Create walking animation**. Walking uses the existing Blender environment and the source rig’s retained skin data. The preview supports playback, scrubbing and camera follow. Download separate in-place and forward GLBs, an FBX with both clips, or an editable Blender file. Inspect deformation and test the exports in your engine before using them in a game. [Canine walking](docs/canine-walking.md)

## Record videos and reopen results

**Download video** records one full orbit from the current view in a supported browser. It targets eight seconds at 30 fps at the preview’s size and exports MP4 or WebM according to browser support. Recording can take longer on a slow renderer. On a walking result, it holds the current pose during capture and restores playback afterward. The video is created in the browser. [Recording details](docs/architecture.md)

Use **Open a saved result** to reopen completed splats, meshes, rigs and walks after a restart. Inputs, exports and job metadata are stored in `outputs/<job-id>/`. The app runs one generation job at a time. Mesh, rig and walk jobs support cancellation. Restart interrupted jobs from their original inputs. To reclaim disk space, delete completed job folders while the app is idle.

## Idol model sources

The app pins the [Idol SDK](https://github.com/speridlabs/idol-sdk/tree/8db700349a5570aac390e4780fa32e3eed6b587a) and downloads the following components into `models/`. [Downloader](model_setup.py)

| Component | Public source | Pinned revision |
| --- | --- | --- |
| Idol and background remover | [speridlabs/idol](https://huggingface.co/speridlabs/idol) | `2731c2291fc65a797c5cb627a5e5526fc1490902` |
| DINOv3 ViT-H+/16 | [LibreYOLO/LibreDINOv3vith16plus](https://huggingface.co/LibreYOLO/LibreDINOv3vith16plus) | `e849a3492905c6dabc89758042bf1402770fb4e6` |
| FLUX.2 VAE | [black-forest-labs/FLUX.2-klein-4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) | `e7b7dc27f91deacad38e78976d1f2b499d76a294` |

The DINOv3 encoder comes from a community bfloat16 mirror. Its expected weight SHA-256 is `34252ee11eeebf00d50c528d53d725672f03ad88ff30cb724ddf3920bf67dc4c`. The FLUX.2 download is limited to the compatible VAE and accompanying documentation. The downloader retains model cards and available license files, including the original DINOv3 license and notice. [Third-party notices](THIRD_PARTY_NOTICES.md)

## Development

```sh
make bootstrap
make check
make doctor
```

Bootstrap installs a separate CPU test environment in `.venv-check`, Chromium and the frontend dependencies. Tests use synthetic fixtures and run without model weights. CI checks Python, frontend build, browser behavior, documentation and repository security. Hardware validation is documented separately. [Development guide](docs/development.md) · [Validation](docs/validation.md) · [Contributing](CONTRIBUTING.md) · [Documentation index](docs/README.md)
