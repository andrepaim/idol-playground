# Skin transfer correction and motion trial

Status: a separate corrected rig and first local moving trials have been produced. Natural-walking acceptance and app integration remain open in #26. Issue #29 covers this correction/probe increment. Existing inputs, source rig, accepted mesh and app behavior are preserved.

## Correction evidence

The upstream transfer copied four weights from the single nearest inferred mesh vertex. The new experimental tool queries the closest source triangle, interpolates its weights and normalizes the strongest four influences. A proper similarity fit aligned the 34 matching joints with maximum error approximately 1.7e-7; 95th-percentile surface distance was approximately 0.00138 model units. The tool rejects inconsistent or mirrored joint correspondence. This changes weights, not joint locations or source geometry.

On the same standing mapping, the original nearest-vertex rig had approximately 4.88% of nondegenerate edges stretched beyond twice their initial length. Closest-triangle interpolation reduced that to 4.29%. Diffusing the source skin field for 4, 16 and 64 iterations reduced it to approximately 3.66%, 3.47% and 2.78%, respectively. The public CLI's 64-step candidate reproduced the result (95th percentile 1.613, 99th percentile 2.892). Nondegenerate-edge counts vary slightly after float32 export around the 1e-6 diagnostic cutoff. The candidate retains all 314,023 vertices / 627,159 triangles, vertex colors, 34 joints, normalized skin weights and at most four influences; the existing GLB rig validator accepted it. These results improve this case, not arbitrary rigs or deformation quality guarantees.

Native processing used the existing Linux/WSL Blender 4.2, NumPy/SciPy and Open3D 0.19 environment. No neural inference or GPU ownership behavior changed. Source and target file digests were checked before/after correction. Owner files, candidates, raw motion, mappings and screenshots stay local.

## Pose export regression

A synthetic native test first reproduced an unrelated BVH action appearing alongside the requested pose. Forcing an active-action export alone was insufficient: Blender's single-armature option still included other actions and could let their rest tracks win the merged clip. The probe now explicitly limits that behavior, creates its own action, preserves quaternion pose values and verifies actual deformed vertex positions after reimport. It also excludes unbound helper meshes. The existing three scalar tests and the new native export regression pass.

Earlier native edge measurements remain measurements of evaluated poses, but a browser preview could have selected an unintended clip. New baseline/candidate comparisons were regenerated with the corrected exporter. This follow-up addresses walking experiment evidence; it does not invalidate the earlier static splat-mesh fidelity measurements.

## Moving trial and remaining gates

Private in-place and forward clips now combine reference-derived contact timing with constrained paw trajectories and inverse kinematics. The selected 72-frame source segment at approximately 120 fps was retimed to a 1.2-second trial with a 0.18-model-unit stride. Four nondeforming contact controls are added in the trial (38 total joints). Both GLBs pass structural skin/appearance validation. Native reimport sampled visible joint motion, identical in-place endpoint matrices and zero root displacement, and forward root displacement of 0.180000 model units. Exported clip times run from zero to approximately 1.2 seconds; game-loop velocity continuity remains a separate check. Foot controls use contact points derived from the paw mesh rather than inferred terminal tails. Internal IK marker error was below approximately 1.3e-5 model units in the sampled trial.

Marker reach is not actual skin-surface contact validation. The phase extraction can synchronize same-side feet; reference gait classification and clip selection still require review before calling this a natural four-beat walk. Body/hind-leg deformation, skin penetration/sliding, bone/joint correction, loop velocity and root-motion playback remain acceptance work. Forward-loop accumulation and game-engine compatibility are not established. The motion trial has not been added as an app feature or published as an owner asset. It is a concrete local review artifact, not completion of #26.

[Full walking plan](natural-walking-plan.md), [correction plan](rig-correction-plan.md), and [tool reproduction](../experiments/walking/README.md).
