# Canine walking (experimental)

After generating or reopening a rig, the app checks whether it matches the reviewed 34-bone canine hierarchy. Supported rigs show four paw assignments. Focus each selector to highlight its bone, correct left/right assignments if necessary, then check the review box. Choose relaxed or normal gait and in-place or forward motion, and select **Create walking animation**.

Walking uses the existing Blender environment (`make setup-rig`); it needs no additional model weights. The completed rig must retain both `rigged.glb` and the internal `skin.fbx` from automatic rigging. Unsupported skeletons show an explanation. Matching hierarchy alone does not establish correct anatomy: inspect all four paws and the output. Only symmetric fore/fore or hind/hind assignment swaps are supported in this first profile.

A new job preserves the original rig and mesh. It transfers continuous skin weights, calibrates a standing pose, solves four-beat paw trajectories, exports, and reimports the result. Progress includes stages, per-frame contact solving, elapsed time and an approximate ETA that learns from completed jobs. Cancel stops the worker before the exclusive slot becomes available again. The server releases cached Idol tensors before walking; the next image generation reloads Idol.

The preview provides play/pause, restart, rest pose, a timeline, playback speed, a floor grid, camera follow, wireframe and skeleton controls. Forward preview accumulates root displacement between cycles. Scrubbing or restarting resets that accumulated travel. Reopen a completed animation through **Recent completed results**.

Downloads include the selected animated GLB, separate in-place and forward GLBs, FBX with both actions, an editable Blender file, and a motion report. Clips start at zero in GLB; Blender actions use frames 1–37 (normal, 1.2 seconds) or 1–49 (relaxed, 1.6 seconds), at 30 fps. The Blend actions are `Walk_inplace` and `Walk_forward`. Export retains vertex colors and skin binding. Engine import, bone conventions and gameplay retargeting remain separate acceptance work.

## Motion and limits

The procedural profile uses the four-beat lateral sequence hind-left → fore-left → hind-right → fore-right, with a 65% stance fraction and conservative body bob. The [University of Minnesota veterinary anatomy reference](https://vanat.ahc.umn.edu/gaits/walk.html) describes the sequential four-beat walk and alternating two/three-foot support. Lift and stride are informed by the preceding private motion trial; this feature does not bundle or redistribute a motion capture file, train a model, or perform general motion retargeting.

The native checks measure the lowest point and a patch centroid in four skin-weight-selected paw regions. They check planted-paw penetration/sliding, loop matrices and root displacement after GLB reimport, plus evaluated motion and appearance/binding in FBX and Blend. They do not prove whole-body collision freedom, biological accuracy, smooth anatomy on arbitrary generated rigs, or game-engine readiness. The inferred rear legs can still look approximate. Parent #26 remains open for broader anatomical mapping and quality work.

## Local validation

The reviewed local dog retains 314,023 vertices, 627,159 triangles and vertex colors. The walking rig adds four nondeforming controls (38 joints total). Both gait speeds passed native export/reimport checks. Relaxed stride is approximately 0.16 model units; normal stride is approximately 0.18. On the normal clip, selected-paw stance penetration after reimport was below 0.00049 model units and maximum planted-frame XY displacement below 0.000009 units at 30 fps. Loop endpoint rotation difference was zero and forward displacement error below 0.000001 units. These are measurements for this input and the selected paw regions, not universal quality guarantees.

Automated coverage includes periodic trajectory position/velocity, four distinct footfalls and continuous support, profile/mapping rejection, source preservation, API setup/busy/cancellation behavior, saved-result reopening, native synthetic export regressions, and Chromium playback/forward-loop/camera-follow acceptance. Owner inputs, generated outputs, screenshots and hardware receipts stay local and are not CI artifacts. See [implementation plan](walking-app-plan.md).
