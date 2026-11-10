# Splat-derived mesh fidelity experiment

Status: authorized experiment following the owner's rejection of distorted TripoSR reconstruction. The saved Idol splat is the geometry/appearance reference; do not reconstruct the original image with another generative model.

## Plan and acceptance

1. Preserve the selected owner splat/photo and previous outputs. Record their hashes privately. Use a separate worktree and ignored output directory; preserve the running app and avoid concurrent owner GPU jobs.
2. Render parallel-axis calibrated stereo pairs around the existing splat, using the same Gaussian renderer as the app. Save RGB, alpha masks, camera intrinsics/extrinsics and exact settings. Exclude held-out comparison angles from fusion. Software WebGL renderer evidence is distinct from CUDA stereo inference.
3. Establish a classical stereo control, then evaluate GS2Mesh's learned DLNR stereo depth if compatible with the local toolchain. Use public pinned source/weights and isolated dependencies; avoid upstream full training/COLMAP wrappers because the splat and camera poses already exist.
4. Filter occlusions/invalid depth and fuse calibrated observations with TSDF. Preserve raw and cleaned meshes. Bake/source appearance only after geometry inspection; do not hide geometry failure behind a texture.
5. Test camera/depth math and filtering with known synthetic geometry. Run actual reconstruction on the saved dog splat. Inspect front, sides, back, leg gaps, head/body proportions and held-out silhouette agreement. Compare settings/variants when evidence justifies a change.
6. Record measured results and limitations. Produce a local mesh and review images when possible. A failed fidelity test is an honest experiment outcome, not an app feature. Do not add UI or rigging unless shape fidelity passes. Integrate reproducible scripts/report through a PR and verify combined-main CI.

## Risks and evidence

A good rendered splat is not necessarily a coherent surface. Stereo may fail on smooth fur, transparent/floaty splats, occlusions or synthetic viewpoint inconsistencies. Silhouette matching alone cannot establish correct interior depth or animation topology. Calibrated-view reprojection tests and multiple inspection angles are required; state all gaps explicitly.

Model execution and CUDA compatibility require actual RTX 3060 evidence; mocked or software-renderer checks cannot establish GPU inference. Keep owner inputs, generated views/meshes, raw receipts, downloaded checkpoints/source and extra environments ignored. No release, paid service, cloud upload, server changes or owner-asset publication are included.
