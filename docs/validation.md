# Validation and evidence

Assess each change's behavior, hardware dependencies, compatibility, storage risks, chosen checks, and limitations. Record the exact revision and environment in its PR or a sanitized receipt. Historical acceptance does not establish a modified GPU path works.

| Change | Minimum relevant evidence |
|---|---|
| Documentation | Accuracy, links/anchors, whitespace, selected CI |
| Pure logic/API/ETA | Meaningful CPU tests and applicable browser acceptance |
| UI/viewer | Real browser checks; visual inspection when automation is insufficient |
| CUDA/model/inference/memory lifecycle | Actual GPU inference plus affected failure/recovery scenarios |
| CI/security guards | Positive/negative routing, gate, history, and privacy regressions |

`make check` uses CPU PyTorch and real Chromium against synthetic API responses and a procedurally generated 128-splat fixture. It covers upload readiness, invalid input, stage/ETA display, errors/retry, downloads, repeated viewer disposal, and mobile overflow. Software WebGL verifies that tested rendering path only; it cannot establish CUDA performance or visual reconstruction quality.

## Real GPU protocol

Use a clean intended revision, downloaded models, and `.venv` with CUDA. Coordinate exclusive GPU ownership. The existing app holds GPU memory while idle: stop only its known idle process before a standalone smoke run, or use a separate GPU with sufficient memory. Never interrupt an active user job.

```sh
make doctor
make test-gpu
```

The smoke script refuses missing model setup, creates a synthetic image, runs 10 steps/65,536 Gaussians, checks binary PLY header, record length/count and finite positions, and saves a sanitized receipt to `.local/gpu-receipt.json`. Images and generated outputs exist only in a temporary directory and are removed afterward. It does not validate reconstruction quality or character readiness.

The receipt includes commit/dirty state, device, driver, CUDA/PyTorch versions, model revisions, settings, stage times, and measured PyTorch peak allocated memory. Allocated memory is not total device usage. Add manual visual observations separately when required. Restart the user's app after releasing the smoke process.

Failed or unavailable required GPU acceptance is a blocker; leave affected work unmerged. A passing CPU CI run does not waive it. Inspect future rigging/export behavior with the additional checks in the [feature plan](game-character-plan.md).

## Apple Silicon splats

Splat generation also runs on Apple Silicon through PyTorch MPS: the app picks CUDA, else MPS, and the SDK samples eagerly there (`IDOL_OPTIMIZE` has no effect). `make doctor` reports `mps`. `make test-gpu` remains CUDA-only. Polygon meshes, stereo conversion and rigging require CUDA.

Recorded on an Apple M5 Max (128 GB unified memory), macOS, PyTorch 2.15.0, the pinned SDK and models, served by `./run.sh`:

| Input | Settings | Total | Sampling |
|---|---|---:|---:|
| SDK example `obj-backpack.webp`, cold start | synthetic, 10 steps, 262,144 Gaussians, seed 42 | 36.0 s | 14.8 s |
| SDK example `fig-fox.webp`, warm | synthetic, defaults (50 steps, 262,144 Gaussians) | 72.0 s | 70.3 s |

Both completed with all sampling steps counted and wrote a PLY, prepared image and camera that the app reopened from saved results. The preview was not visually inspected, and reconstruction quality was not compared with CUDA output.
