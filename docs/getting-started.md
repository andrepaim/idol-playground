# Getting started

Use Linux, Python 3.11, Node 22.23.1, uv 0.12.3, Git, and Make. GPU generation requires an NVIDIA CUDA GPU, or an Apple Silicon Mac for splats only (see [Apple Silicon](validation.md#apple-silicon-splats)); the local acceptance target is an RTX 3060 with 12 GB VRAM. Other platforms are not yet accepted targets.

```sh
git clone https://github.com/andrepaim/idol-playground.git
cd idol-playground
make bootstrap
make check
make doctor
```

Bootstrap installs locked dependencies into `.venv-check`, Chromium for browser acceptance, and `node_modules`, then builds `dist`. It does not download model weights or alter `.venv`, the separate CUDA environment. On minimal Linux installations, install browser system libraries with `.venv-check/bin/python -m playwright install --with-deps chromium`; this may require system package privileges.

For real generation:

```sh
make setup-local
make models
make run
```

Open http://127.0.0.1:8000. `make setup-local` installs the CUDA SDK into `.venv` from `uv.lock`. `make models` downloads about 5 GB of pinned public assets; no Hugging Face login is required. The first generation can download missing weights if explicit setup was skipped. Internet access is needed during setup; cached inference loads local files.

`make doctor` selects `.venv` if present, otherwise `.venv-check`, and reports missing dependencies/models. `.venv/bin/python scripts/doctor.py --require-gpu` fails when full generation readiness is absent. Check `nvidia-smi` and CUDA-enabled PyTorch if generation is unavailable; on a Mac, `doctor` reports `mps`. Close other GPU applications or use fewer Gaussians for memory pressure.

The app binds to loopback. `PORT=8002 make run` selects another port. Export variables in your shell; `.env.example` is documentation and the server does not automatically load `.env`.

Inputs and results live in `outputs/<job-id>`. Do not delete or move active-job directories. Completed `job.json` survives restarts; interrupted inference cannot currently resume. For splat-derived GLB output, run `make setup-splat-mesh splat-mesh-models` and follow [mesh setup](mesh-generation.md). Optional [automatic rigging](automatic-rigging.md) is available after mesh inspection; authored animation and engine acceptance remain separate work.
