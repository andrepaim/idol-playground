# Third-party components

This repository contains application source and dependency/model references. It does not redistribute the model weights. No license grant for the app's own source has been selected yet; public repository visibility is not a source license.

- [Idol SDK](https://github.com/speridlabs/idol-sdk) and [Idol model](https://huggingface.co/speridlabs/idol): pinned source and model cards define their applicable terms.
- [DINOv3 mirror](https://huggingface.co/LibreYOLO/LibreDINOv3vith16plus): retains the original DINOv3 license and attribution; do not treat a community mirror as a replacement license.
- [FLUX.2 Klein](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B): the compatible VAE is downloaded with its Apache-2.0 license material.
- [GaussianSplats3D](https://github.com/mkkellogg/GaussianSplats3D) and [Three.js](https://github.com/mrdoob/three.js): MIT-licensed viewer dependencies; preserve bundled notices.
- Validation routing, Markdown link checking, and repository guard patterns were adapted from the owner's DistillPod project at the owner's request.

Model cards and available notices are retained by the downloader. Review upstream terms when changing pinned revisions or distributing assets. The optional mesh backend installs pinned TripoSR code/weights, DINO configuration, U2Net/rembg, PyMCubes, xatlas, trimesh, and fast-simplification. Preserve their respective upstream licenses; TripoSR source/model use MIT terms and PyMCubes uses BSD terms. UniRig integration is subsequent work.

Automatic rigging optionally downloads pinned [UniRig](https://github.com/VAST-AI-Research/UniRig) code and [weights](https://huggingface.co/VAST-AI/UniRig) (MIT notices retained beside local assets), plus the OPT architecture configuration. Its isolated environment includes Blender/bpy (GPL) and official prebuilt CUDA extensions; dependency licenses remain applicable. No checkpoints or third-party binaries are vendored in this repository. See `backends/unirig/uv.lock` and `docs/automatic-rigging.md`.
