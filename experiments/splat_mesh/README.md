# Reconstruct a mesh from saved Idol splats

This optional experiment leaves the app's current generation modes unchanged. It renders calibrated views of an existing splat, estimates stereo depth, fuses a surface and compares it with held-out splat views. Read the [results and limitations](../../docs/splat-mesh-results.md) first.

Requires the existing app and CPU/browser check environment, Linux x86-64, Python 3.11 and NVIDIA CUDA for DLNR. The locked experiment environment is separate from Idol, TripoSR and UniRig:

```sh
UV_PROJECT_ENVIRONMENT="$PWD/.venv-stereo" uv sync --project experiments/splat_mesh --locked --python 3.11
mkdir -p .local/vendor .local/models
git clone https://github.com/yanivw12/gs2mesh.git .local/vendor/gs2mesh
git -C .local/vendor/gs2mesh checkout --detach 560f3e8a2349aaad24fe9444ef1ca2770aeec5ab
curl --fail --location https://github.com/David-Zhao-1997/High-frequency-Stereo-Matching-Network/releases/download/v1.0.0/DLNR_Middlebury.pth --output .local/models/DLNR_Middlebury.pth
printf '%s\n' '57e46b8fed66b685f732b730ebffd71998dcabea49f8443ca77e015419f6ae18  .local/models/DLNR_Middlebury.pth' | sha256sum --check
```

Use a new ignored output directory for each source/settings run; cached disparity files are indexed by view and must not be reused with different cameras, inputs, models or iteration settings. Select the actual existing PLY path in the first command. The local app must be running on port 8000; capture intercepts only its research browser's requests and does not start app generations or modify server code.

```sh
.venv-check/bin/python experiments/splat_mesh/render_views.py --splat /absolute/path/to/object.ply --output .local/splat-test/views
.venv-stereo/bin/python experiments/splat_mesh/reconstruct.py --views .local/splat-test/views --output .local/splat-test/dlnr --method dlnr --source .local/vendor/gs2mesh --checkpoint .local/models/DLNR_Middlebury.pth
.venv-stereo/bin/python experiments/splat_mesh/refine.py --views .local/splat-test/views --depths .local/splat-test/dlnr --output .local/splat-test/refined --largest-component
.venv-stereo/bin/python experiments/splat_mesh/evaluate.py --views .local/splat-test/views --mesh .local/splat-test/refined/mesh.ply --output .local/splat-test/refined/evaluation
.venv-check/bin/python experiments/splat_mesh/inspect_meshes.py --views .local/splat-test/views --mesh .local/splat-test/refined/mesh-reference.glb --output .local/splat-test/refined/inspection
```

`--largest-component` is an explicit single-connected-subject choice. It can discard detached accessories or body parts; inspect raw.ply and the retained result. The source splat and original outputs are never overwritten. For a classical control, run reconstruct.py with `--method sgbm` and its own new output directory, omitting source/checkpoint arguments.

The renderer uses the app's PLY coordinate convention, fixed camera radius/target and framing. Different input scales may need camera/depth-range adjustments before the experiment is meaningful. Calibration tests do not prove that an arbitrary splat forms a coherent surface.

The reconstruction records raw mesh, RGB colors, disparities and filtered depth. Refine writes `mesh-reference.glb` and `mesh.ply` in source coordinates, and `mesh.glb` rotated to normal glTF Y-up. Colors are embedded as linear float attributes with an unlit material. No UV texture, skeleton or animation is generated.

Optional private review artifact, after inspecting metrics/images:

```sh
.venv-check/bin/python experiments/splat_mesh/publish_review.py --result .local/splat-test/refined --output /absolute/path/to/app/outputs/NEW-UNIQUE-DIRECTORY --web-dist /absolute/path/to/app/dist
```

The destination must not exist. It creates `review.html`, `comparison.png`, `mesh.glb` and measurements for the existing localhost static server; it does not register an app job or publish assets remotely. Open `/outputs/NEW-UNIQUE-DIRECTORY/review.html`. Rebuild/regenerate the review artifact if frontend bundle filenames change.

Checks:

```sh
.venv-check/bin/python -m pytest -q tests/test_splat_mesh.py
.venv-stereo/bin/python -m unittest discover -s experiments/splat_mesh -p 'test_*.py'
```

DLNR's source license is retained in the ignored clone. No upstream source, weights or owner media are vendored here. Browser software rendering is separate from actual CUDA stereo evidence. Keep all captures, model files and generated results ignored.
