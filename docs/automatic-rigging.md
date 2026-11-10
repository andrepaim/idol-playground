# Experimental automatic rigging

Generate a **Textured mesh · .glb**, inspect its anatomy, then click **Auto rig · experimental**. The app runs UniRig's learned skeleton prediction and skinning sequentially on the local GPU and merges the result into the original textured mesh. It preserves the static mesh as a separate job.

## Setup

```sh
make setup-rig rig-models
npm run build
./run.sh
```

Install mesh generation first as described in [mesh generation](mesh-generation.md). Rigging uses its own `.venv-unirig`, Python 3.11, PyTorch 2.5.1/CUDA 12.4 and Blender 4.2 Python module. This profile supports Linux x86-64/WSL with NVIDIA CUDA. Official prebuilt FlashAttention/scatter/cluster wheels avoid a system CUDA compiler requirement. Downloads include approximately 5.8 GB of UniRig checkpoints plus environment packages; allow extra disk space for caches and exports. No Hugging Face login or cloud service is needed.

The app reports rigging setup separately from reconstruction. `make rig-models` must finish before the rig button is enabled. Inference uses local pinned weights/configuration with Hugging Face offline mode and cloud logging disabled. Source, checkpoints and environments remain ignored.

## Preview and downloads

Stages cover mesh preparation, skeleton prediction, bone preparation, skinning, export and independent reimport checks. ETA starts approximately and learns successful stage durations in `outputs/.rig-timings.json`. These operations have no reliable internal percentage; the UI leaves their progress indeterminate. Cancellation stops/reaps the current phase before another GPU job can start. Starting rigging releases any cached Idol weights.

The completed viewer offers **Skeleton**, **Test bend**, wireframe and reset controls. Test bend plays a short diagnostic bone rotation, then returns to the rest pose. It demonstrates that the exported skin binds to bones; it is not an authored animation or a walking cycle.

Downloads:

- `rigged.glb`: embedded texture, skin, skeleton and diagnostic animation.
- `rigged.fbx`: skeleton, weights, embedded texture and diagnostic animation.
- `character.blend`: editable mesh, armature, material and diagnostic action with packed images.
- Original static mesh: preserved without a skeleton or animation.

The job also retains `rig.json` with actual bone/triangle counts, peak PyTorch allocation per model, deformation statistics, warnings and export reimport results. Internal FBX/NPZ files, texture intermediates and per-phase worker logs stay in the ignored job folder for local diagnosis. Interrupted jobs cannot resume automatically.

## Validation and limits

The pipeline rejects missing/uncompleted source meshes and incomplete setup. Workers have per-phase timeouts, propagate errors, verify expected files, and run without upstream shell wrappers. This WSL build's Blender module can crash during interpreter teardown; the phase adapter flushes and exits only after explicit operation/result checks, while exceptions remain nonzero failures.

Completed GLBs must contain finite geometry/UVs, embedded textures, a valid acyclic joint hierarchy, finite nonsingular inverse-bind matrices and normalized nonnegative weights with at most four influences per vertex. A diagnostic rotation must move weighted vertices. All three exports are independently reimported and checked for bones, binding, normalized weights and readable material textures. Unit/API tests cover invalid rigs, source/setup/busy handling, persistence, failed phases and ETA; browser acceptance covers skeleton/playback/export controls and viewer switching. Actual GPU and visual acceptance is additionally required for changed inference paths.

Automatic rigging does not repair missing/fused limbs, infer correct game topology, guarantee anatomical joints, or produce standard engine humanoid bone names. The result uses generic bone names. Inspect neutral and bent poses in the viewer and Blender before engine use. Engine import/retargeting and authored animations remain separate work; see the [character roadmap](game-character-plan.md) and [implementation plan](auto-rig-implementation.md).

## Pinned sources

| Component | Source | Revision |
|---|---|---|
| UniRig code | VAST-AI-Research/UniRig | `6793c6640ff01c8fb389f3993434124bb43d2933` |
| Skeleton and skin weights | VAST-AI/UniRig | `36842e2b5947e9e60f89275b83208c8e74071c63` |
| OPT architecture configuration only | facebook/opt-350m | `08ab08cc4b72ff5593870b5d527cf4230323703c` |

No separate OPT language-model weights are needed; trained parameters are included in the rigging checkpoint. See [third-party notices](../THIRD_PARTY_NOTICES.md).
