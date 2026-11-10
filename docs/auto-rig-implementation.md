# Automatic rigging implementation

Status: implemented and tested on the RTX 3060; PR #18 awaits final switching acceptance and merge. See [validation evidence](rig-validation.md). Authorized continuation of the photo → mesh → cleanup → rig approach. Build on merged textured mesh support (PR #17). Issue #5; parent feasibility #2 remains open until the full benchmark criteria are met.

## Behavior and acceptance

After inspecting a generated mesh, the user can start an explicitly experimental local automatic-rigging job. Run both pinned UniRig stages sequentially, retain the original textured mesh, and export a separate textured/skinned GLB, FBX and editable Blender file. Display actual stages and approximate ETA; allow cancellation through the same exclusive GPU slot. Never mark a static mesh as rigged or imply a successful export guarantees game-ready anatomy.

Use a skeleton overlay and a diagnostic bend clip in the GLB viewer. Validate real bones, parent hierarchy, finite inverse-bind matrices, normalized skin weights, four influences per vertex, texture retention and movement of weighted vertices. Preserve the static source and all previous job artifacts. Invalid/missing source jobs and unavailable setup must fail before allocating a new worker.

## Steps

1. Pin a separate Linux x86-64 Python 3.11/CUDA 12.4 environment, official prebuilt attention/scatter/cluster wheels, source revision and public skeleton/skinning/OPT configuration assets. Keep all inference offline with cloud logging disabled.
2. Implement bounded phase subprocesses: extract mesh, predict skeleton, extract predicted skeleton, predict skin, merge into original texture/UV mesh and export. Use argument arrays, explicit result checks and cancellation/reaping. Do not invoke upstream shell wrappers. Handle this WSL build's bpy teardown crash by flushing and exiting only after successful phase execution; exceptions remain failures.
3. Add independent readiness and source-job validation, persisted rig jobs/files, shared GPU ownership/cache release and measured per-stage ETA.
4. Extend the mesh viewer and UI with experimental rigging, skeleton overlay, diagnostic bend playback and alternate export downloads. Keep existing splat/static mesh behavior.
5. Meaningful tests first for hierarchy/weights/export integrity, orchestration/cancellation/source validation and UI behavior. Run actual skeleton+skin/export/reimport on generated humanoid and quadruped meshes and a known-good humanoid. Inspect neutral and bent results. Finish current-main integration, PR merge and combined-main CI.

## Risk and boundaries

This is learned experimental rigging with generic bone names, not a standard humanoid retargeting preset, animation controller or authored walk cycle. Reconstruction can fuse limbs or omit anatomy. Validate deformation rather than accepting skeleton presence alone. A simple diagnostic clip proves binding and exercises the rig; it is not a usable game animation. Engine integration remains issue #7.

GPU compatibility, memory, child-process ownership and Blender export require actual RTX 3060 evidence on the candidate. Preserve owner inputs and keep captures, model caches, generated assets and raw logs ignored. Wait for active owner jobs before GPU checks or server restarts. No releases, paid services, cloud upload or owner-asset publication.
