# Automatic rigging validation

Inference/runtime candidate: `e792e4391086975ecb2d4fd8016481fdf1ceaf3b`. RTX 3060 12 GB, driver 610.88, Linux/WSL, Python 3.11, isolated PyTorch 2.5.1/CUDA 12.4, Blender 4.2 module. Date: 2026-11-10. PR #18 records acceptance and combined-main CI.

## Actual photo-to-character runs

All three photos went through the real mesh and rigging UI/API, without mocked inference. Mesh settings were grid 192, 25,000-triangle cap, 1024px texture, seed 42. Both learned UniRig stages ran sequentially. Times below cover rigging, after mesh generation.

| Input | Rig time | Bones | Skeleton peak allocation | Skin peak allocation |
|---|---:|---:|---:|---:|
| Owner-provided sitting dog | 60.0s | 35 | 3997 MiB | 4215 MiB |
| Full-body cartoon humanoid | 61.8s | 28 | 3997 MiB | 4192 MiB |
| Horse | 57.2s | 23 | 3997 MiB | 4185 MiB |

Each completed GLB contained validated joints, finite nonsingular inverse-bind matrices, normalized skin weights, embedded texture and a diagnostic animation. Diagnostic rotation moved weighted vertices in each case. GLB, FBX and Blender exports independently reimported with the expected bone counts, binding and readable material textures. All three actual browser downloads had the expected file signatures.

The actual UI showed stage/ETA changes, skeleton overlay, diagnostic playback, wireframe and reset, without JavaScript page errors. Cancelling a live skeleton job stopped its phase, preserved the static mesh and allowed another rig job. Screenshots, inputs, exports and raw receipts remain ignored locally. Browser rendering used software WebGL; CUDA was exercised by the actual model processes.

Visual review found recognizable prototypes, plausible major body/limb joint placement on the humanoid and horse, and visible bound deformation. Paçoca's sitting pose remains difficult: inferred anatomy is incomplete and the rig does not repair it. The sample rotation is a binding diagnostic, not proof that every joint bends naturally or that the character can walk.

## Authored humanoid baseline

The upstream UniRig `tira.glb` asset was fetched from source revision `6793c6640ff01c8fb389f3993434124bb43d2933` and verified against its Git LFS SHA-256 `8e5a282d0a99c61a8d2439496057b15b0c6ea02643c16da2dcbec85571157799`. Local preparation removed seven constant-material cosmetic expression primitives and converted unlit material declarations to standard PBR, preserving body geometry, UVs and base-color textures. This prepared baseline has 99,559 triangles.

Actual prediction produced 52 bones, approximately 3999/4261 MiB peak skeleton/skin allocation and a measurable diagnostic deformation. All three exports reimported with 52 bones, normalized binding and readable textures; GLB retained 15 embedded images. Skeleton prediction and skinning took about 26.0s and 22.5s inside their isolated phases.

The unlit-material attempt failed FBX texture validation before normalization. Consequently this evidence covers the application's TripoSR PBR outputs and a prepared PBR humanoid; it does not establish arbitrary shader/material import compatibility. Raw benchmarks and their intermediate files were preserved locally.

## Model switching

The same API server completed Idol → rigging → Idol in 43.0s / 65.7s / 34.1s (Idol synthetic mode, 10 steps, 65,536 Gaussians, seed 42). Cached Idol status changed loaded → released → reloaded. Whole-GPU memory after those jobs was approximately 6796 → 3100 → 6796 MiB, including desktop/driver usage. The rig worker exited before the next generation; all jobs completed successfully. This is observed switching evidence, not a general performance guarantee.

## Automated validation and boundaries

38 API/logic tests, 30 infrastructure tests, 6 Chromium browser cases, and 3 isolated TripoSR surface/export regressions passed, together with Ruff, ESLint, documentation/link checks, repository data guard and full-history secret scanning. Coverage includes invalid joint hierarchy/references, singular bind matrices, corrupt/unnormalized weights, missing setup/source, exclusive ownership, source preservation, persisted rig metadata, phase failures, ETA history and viewer controls/lifecycle.

This establishes an experimental local reconstruction-and-rigging path. Generic bone names, inferred topology/anatomy, retargeting, engine import, collisions/LODs and authored animation quality still require separate work. Parent feasibility #2 remains open for broader quality acceptance; engine work remains #7. Refer to [automatic rigging](automatic-rigging.md) and the [character roadmap](game-character-plan.md).
