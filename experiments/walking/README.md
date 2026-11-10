# Walking feasibility probe

This is a standing-pose experiment for the [natural walking plan](../../docs/natural-walking-plan.md), not an app walking feature. It intentionally uses explicit, externally reviewed joint mapping. It does not automatically infer anatomy, solve foot contact, repair weights or certify natural movement.

Use the existing `.venv-unirig` Blender environment. The supported reference dialect is the publisher's raw dog BVH, imported Y-up, and a target rig with X anatomical forward / Z up in armature coordinates. Other coordinate conventions need explicit adaptation; do not assume this handles arbitrary rigs.

```sh
.venv-check/bin/python -m pytest -q experiments/walking/test_pose.py
.venv-unirig/bin/python experiments/walking/pose.py \
  --input /path/to/rigged.glb --motion /path/to/dog_quad_walk_001.bvh \
  --mapping /path/to/reviewed-mapping.json --frame 100 \
  --output /path/to/new-review-directory
```

Mapping JSON contains `source_hips`, `source_chest`, `target_hips`, `target_chest`, and `joints`: a list of objects with `target` and `source` bone names. Each may set `hold: true` to retain its original global orientation, or `degrees` for an explicit sagittal direction measured from +X toward +Z. Review anatomical correspondence, including front wrists versus rear hocks; names alone are insufficient. Source headings are aligned horizontally before posing. The output directory must not exist.

The tool preserves input bytes and emits `report.json` with private provenance/mapping plus `pose.glb`, a two-frame constant candidate pose. Play its `Standing feasibility` clip to see the deformed pose: a glTF viewer's static rest display is not the candidate pose. The clip is a pose-review artifact, not walking. Linear skinning is evaluated in Blender; edge lengths are compared with the original evaluated mesh. The model may remain unsuitable even with low edge stretch. Assess contact, joint anatomy and surface appearance independently.

Obtain the reference from the [publisher record](https://doi.org/10.6084/m9.figshare.24968946) (CC BY 4.0). Archive `raw_bvh_data.zip`, published MD5 `746d592726eb7411f084518bfa1f3791`; retain author attribution and modification notes for derived motion. Raw archives, owner rigs, mappings, generated poses and logs remain ignored. No owner assets are redistributed.

See [current findings](../../docs/walking-feasibility.md).
