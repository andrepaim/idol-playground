# Standing-pose feasibility for natural walking

Status: the initial standing/deformation gate has not passed for the approved seated dog rig. Natural walking remains unimplemented. This bounded experiment does not change the app, its accepted reconstruction, or existing rig exports. Parent issue #26 remains open; issue #27 tracks the reproducible probe.

## Evidence

Native Blender 4.2 processing ran on the existing Linux/WSL machine using `.venv-unirig`; these are CPU pose/deformation checks, not new CUDA inference or natural-motion benchmarks. The source has 34 bones, 314,023 vertices and 627,159 triangles. Its input digest was checked before and after the probe and remained unchanged.

The publisher's raw BVH archive (DOI 10.6084/m9.figshare.24968946, CC BY 4.0) downloaded and matched its published MD5. The `dog_quad_walk_001.bvh` reference imported at approximately 120 fps. This establishes readable reference motion; clean cycle segmentation, paw-contact quality and a complete reference retargeting baseline remain unvalidated.

Trials corrected the reference Y-up/target Z-up conversion, aligned horizontal anatomical heading, corrected differing joint names and tested explicit sagittal poses. An early incomplete mapping was discarded. A corrected reference-direction pose still produced visible deformation and a 95th-percentile edge-length ratio of 2.48. A more conservative candidate retained head/front-leg orientation and set reviewed rear-leg angles; 45,965 of 941,848 nondegenerate edges (4.88%) stretched beyond twice their baseline length. Its 95th percentile was 1.96 and 99th percentile 5.07. These are diagnostic observations, not calibrated acceptance thresholds.

The candidate was exported as a constant two-frame clip and inspected in Chromium/Three.js with software WebGL. Playback matters: a static glTF rest-pose display showed the original seated dog and would have concealed the failed candidate. Visible belly/rear-leg distortion and incomplete grounded support reject this pose as the basis for a natural-walking claim. Screenshots, mappings, logs and raw measurements remain local.

These trials do not prove the rig is impossible to correct, nor isolate skin weights from all residual joint-placement/mapping errors. They do establish that the tested pose-transfer approaches fail the current visual gate. No paw IK, natural loop, game-engine compatibility or walking export acceptance is claimed.

## Next dependency

Audit joint placement and regional weight distribution around hips, belly and hind legs; create a separate corrected rig/weight candidate, retain the static reference, and repeat the standing gate. Establish four supported paws without severe surface collapse, then proceed with reference-cycle segmentation, contact-aware retargeting and loop validation. A suitable authored/reference rig and another standing generated subject should isolate retargeting errors from the seated reconstruction. The app animation control remains dependent on those checks.

The [probe instructions](../experiments/walking/README.md) reproduce pose measurements using an external source/mapping; the [full plan](natural-walking-plan.md) defines remaining milestones. New tests cover invalid/repeated mappings, nonfinite/degenerate direction handling, coordinate rotation and deformation summaries. Existing CPU/API regressions remain required; changing inference or GPU ownership requires fresh hardware acceptance.
