# Splat-derived mesh experiment: results

Status: the local fidelity experiment produced a mesh that preserves the tested dog's shape substantially better than the rejected independent reconstruction. The reviewed workflow is now integrated as the app's preferred mesh method; TripoSR remains an explicit legacy option. The results below describe the original bounded experiment; see [integration validation](splat-mesh-integration-validation.md) for the app path.

## What ran

The input was the saved Idol result for the owner-provided sitting dog: 262,144 Gaussians, real-photo mode, 50 steps, seed 42. The original photo was not passed through another image-to-3D generator.

The app's unchanged Gaussian renderer generated 36 calibrated parallel-camera stereo pairs: 512px square, 42-degree field of view, camera radius 1.5, baseline 0.075, twelve azimuths at each elevation of -20, 15 and 50 degrees. Eight additional views at elevation 15 degrees and azimuths offset from the training positions were withheld from fusion.

Stereo used the DLNR Middlebury model shipped with [GS2Mesh](https://github.com/yanivw12/gs2mesh), followed by left/right consistency filtering and Open3D TSDF fusion. This is an adaptation of its stereo/fusion approach, not a run of its full training/COLMAP pipeline. Calibrated poses already existed, so camera estimation and Gaussian training were unnecessary. Opaque foreground threshold was 0.75, left/right tolerance 1.5px, valid depth range 0.75–2.25.

Source: GS2Mesh commit `560f3e8a2349aaad24fe9444ef1ca2770aeec5ab`. Official `DLNR_Middlebury.pth` release v1.0.0 SHA-256: `57e46b8fed66b685f732b730ebffd71998dcabea49f8443ca77e015419f6ae18`.

Core reconstruction code was tested at `8881264`; CPU postprocessing/export and review tools at `08723e7`. Later changes document results. The neural inference path was unchanged between those revisions.

## Measured results

| Variant | Mean held-out silhouette IoU | Minimum IoU |
|---|---:|---:|
| Classical SGBM stereo, 0.004 voxel | 93.54% | 91.88% |
| Learned DLNR stereo, 0.004 voxel | 94.52% | 92.54% |
| DLNR, 0.002 voxel, small-fragment cleanup | 95.27% | 94.01% |
| DLNR, 0.002 voxel, largest connected subject | **95.78%** | **94.36%** |

These compare binary mesh silhouettes with the source splat's alpha masks, using the exact same withheld cameras. They measure fidelity to the splat's outline, not anatomical correctness or general 3D accuracy. They do not quantify additional camera elevations or unseen real-world surfaces.

Visual inspection of matched front, side and back views found the head/muzzle, seated torso, major leg proportions and leg separation largely preserved. Fine features are softer than the splat; tail/paw edges and some surfaces remain rough. Keeping the largest component removed detached accessory/noise fragments, including disconnected collar/leash pieces. Raw meshes and all excluded geometry are preserved locally.

The selected prototype has 314,023 vertices and 627,159 triangles. It is not watertight and has no UV map, texture image or skeleton. Appearance uses embedded linear vertex colors with an unlit glTF material. A separate upright Y-up GLB is supplied for normal viewers; the original-coordinate GLB/PLY remains available for calibrated comparisons. It is a dense prototype requiring topology/appearance processing before game use.

## Environment and timings

Actual RTX 3060 12GB, driver 610.88, PyTorch 2.5.1/CUDA 12.4. Learned stereo/fusion took 26.28s across all 36 pairs and reported 590 MiB peak PyTorch allocation. Classical stereo/fusion took 4.63s. Final CPU refusion/cleanup/export took 3.04s. These exclude view capture and evaluation.

View capture took 347.48s using Chromium's ANGLE/Vulkan SwiftShader software renderer. This is the main experimental bottleneck and is not a CUDA rendering speed measurement. Viewer inspection identified the same SwiftShader renderer. Existing app state/model cache and owner outputs were preserved; inference pauses between pairs if the app reports an active job.

Local acceptance: 41 root API/logic tests, 30 infrastructure tests, 6 existing browser cases and one isolated real GLB color/geometry export regression passed. Camera tests cover baseline disparity, invalid observations and the app's negative-Y-up convention. Actual exported GLBs loaded in the browser; the private review page's orbit, wireframe/reset and download worked over the real local HTTP server without JavaScript page errors. Ruff, ESLint, documentation checks and repository security guards passed.

## Review and next decision

The local review artifact contains the interactive upright mesh, measurements, camera-matched images and download. Owner inputs, derived images, meshes, raw depth/disparity and private source hashes remain ignored and were not published to GitHub.

This is sufficient to review splat-derived meshing as the next direction. It does not establish reliable conversion for arbitrary images or game-ready characters. The integrated path preserves this fidelity check and offers experimental rigging. Capture speed, holes, topology/texture baking and broader subject coverage remain open.

See the [reproduction instructions](../experiments/splat_mesh/README.md) and [experiment plan](splat-mesh-experiment.md).
