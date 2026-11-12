# Template-rig vertical slice and reconstruction comparison

Feasibility spike for [issue #72](https://github.com/andrepaim/idol-playground/issues/72), run 2026-11-12 at the owner's request, with M2 Idol integration ([#68](https://github.com/andrepaim/idol-playground/issues/68)) paused. It asks two questions: can a *new* image-derived character become playable in the existing Three.js runtime, and is the current reconstruction route the right one? This is go/no-go engineering evidence for one development subject. It is not tier acceptance, corpus evidence or the owner's visual judgement.

## Result in brief

- **Slice A (rig and motion): go.** The licensed Shiba development subject from the [baseline](character-baseline.md) became a controllable, colour-preserving, walking character in the unchanged M1 runtime, without UniRig inference. A 24-joint quadruped template fitted from geometry replaces the arbitrary generated skeleton. The procedural-gait output passes every numeric land-motion gate in the [acceptance plan](image-to-playable-validation.md#land-motion).
- **Slice B (reconstruction): the alternative is better on this subject.** TRELLIS-image-large produced a single watertight 208,758-triangle mesh with four clean legs in about 30 s of RTX 3060 inference. The current Idol splat → stereo → fusion route took 465 s for an 855,576-triangle open mesh with ragged surfaces. TRELLIS's mesh then went through Slice A unchanged and also became playable.
- **Main finding:** the baseline's blocker, a 32-bone UniRig skeleton that the fixed 34-bone walking profile correctly refuses, disappears when the skeleton comes from a per-family template. Every fitted character shares joint names, hierarchy and rest conventions, so motion transfers without per-character semantic mapping.

## Slice A: template skeleton pipeline

Tooling: [`experiments/vertical_slice`](../experiments/vertical_slice).
- **`quadruped_fit.py`:** pure-Python geometry helpers, tested in CI.
- **`slice_blender.py`:** runs the pipeline in the checksum-verified official Blender 4.2.0 executable from [reference assets](character-reference-assets.md).
- **`capture_review.py`:** renders fixed review frames and drives the gameplay sample.

| Step | Method |
|---|---|
| Simplify | Blender collapse decimation of the dense vertex-coloured mesh to about 48,000 triangles |
| Silhouette | 8 orthographic views, dense vs prepared, Cycles alpha masks |
| Canonical frame | 2D PCA body axis; the head end has more upper-body surface than the tail end |
| Paws | Connected floor-contact blobs on a grid of 1.25% of body length (faces sampled); exactly four, forming fore and hind pairs, or `AnatomyError` |
| Template fit | Fox reference rig (Khronos sample: model CC0, rig/animation CC-BY 4.0), 24 joints. Spine, neck, head and leg sockets keep the joint's relative height within the body's midline cross-section. Legs follow slice-traced limb centrelines. Shoulder/hip sockets are mirrored. Paw joints sit at ≥ 15% of leg height. The tail follows geodesic rings from its tip |
| Skin | Blender heat weights on the prepared mesh (a voxel-proxy fallback exists but was not needed); limited to 4 influences and normalised |
| Motion | Fox `Walk` retargeted through per-bone rest-relative world rotations. Wrists and ankles are pinned by IK to planted paths that move back at body speed during stance, with paw bones held flat; baked to linear keys |
| Export | GLB with one in-place `Walk_inplace` clip, runtime forward +X; independent accessor-level skin check |

Results per input mesh, using the procedural gait: a 4-beat lateral-sequence dog walk with 65% stance (order left hind, left fore, right hind, right fore). It keeps 35% of the Fox body motion, and its stride keeps the paw sweep within reach.

`L` is the prepared-mesh bounding-box diagonal. Motion is sampled at ~60 Hz over one 0.708 s cycle using skinned paw vertices, with stance taken from the clip's planted-path annotation as the validation plan requires.

| Measure (gate) | Baseline mesh (Idol → stereo) | TRELLIS mesh |
|---|---:|---:|
| Source triangles | 855,576 (open, 4 components) | 208,758 (watertight, 1 component) |
| Prepared triangles (target ≤ 50,000) | 47,999 | 48,000 |
| Silhouette IoU mean / min (≥ 0.95) | 0.9955 / 0.9948 | 0.9997 / 0.9992 |
| Paws found / tail found | 4 / yes | 4 / yes |
| Unbound vertices; max weight-sum error; max influences | 0; 1.3e-7; 4 | 0; 1.3e-7; 4 |
| Worst stance sliding / L (≤ 0.02) | **0.0048** | **0.0171** |
| Worst penetration / L (≤ 0.005) | **0.0004** | **0.0006** |
| Loop position seam / L (≤ 0.005) | **0** | **0** |
| Highest paw sole during stance / L (no gate) | 0.0175 | 0.0130 |
| Max IK reach error / L | 0.0135 | 0.0106 |
| Edges stretched > 2×; 99th-percentile ratio | 0.38%; 1.56 | 0.12%; 1.40 |
| GLB size | 1.65 MB | 8.67 MB (flat-shaded faces split vertices: 143,935) |
| Slice A CPU time (one run) | 15.7 s | 8.3 s |

The same rig driven by raw FK retargeting, without IK, fails the contact gates by a wide margin (baseline mesh, Fox timing: sliding 0.088, penetration 0.031). Keeping the authored Fox contact timing with IK also passes the numeric gates (sliding 0.0134, penetration 0.0005), though paw soles rise up to 0.027 × L during its short stances. All figures come from the final code; procedural reruns reproduced byte-identical GLBs.

Defects found and fixed during the spike, each with a regression test:
- **Asymmetric hip sockets.** Slice tracing put one hip socket 6.5 cm forward of the other; sockets are now mirrored.
- **Hind paws not owned by the paw bone.** A floor-level paw joint left 41–45% of each hind sole weighted to the rotating hock bone; the paw joint now stays above the sole.
- **Low-poly template sections.** Sparse Fox midline sections produced runaway joint heights; the template surface is now sampled densely, with a fallback to back-height scaling.
- **Merged front paws.** TRELLIS's front paws stand close together and merged on the original grid, so the default cell was halved.

### Browser and gameplay

Each sample was assembled from the **unchanged** `web/playable-viewer.js` and `web/character-controller.js`, with an experiment manifest (`profile: quadruped-fox24-experimental`) replacing the canine profile gate. Chromium 158.0.8127.18 with SwiftShader, so this is functional evidence only, with no performance claim. For both meshes:

- **Load:** no page errors and no external requests.
- **Movement and reset:** W moved the character continuously in the camera-relative direction, it stopped on release, and reset returned it to the origin.
- **Collision:** driving into the box obstacle stopped it at exactly x = 2.0 (the obstacle face minus the controller radius), and it then slid along the face.

### Visual self-review (not the owner's acceptance)

Review frames come from five fixed views × eight phases, plus skeleton overlays. In every frame, both characters keep the Shiba's identity, colours and curled tail, with no tearing, detached limb or ragged crease. This walk bends the neck far less than the baseline's diagnostic UniRig bend did, so it is not a like-for-like test of that crease.

- **Fox timing:** a faithful retarget of a stylized fox walk. It has deep body pitch, a mid-cycle lunge, short stance and front legs crossing in front view (foxes single-track). It does not read as a dog walking.
- **Procedural gait:** reads as an ordinary dog walk, with a level back, legs in sequence and two or three paws planted at once. Paws stay stiffly flat during swing, and the body is slightly mechanical.
- **TRELLIS character:** cleaner surfaces and colours. Its fitted front-leg elbow joint appears slightly ahead of the limb in the right-side skeleton overlay at phase 0, which needs a closer check.

Self-scores on the [rubric](image-to-playable-validation.md#4-visual-assessment-rubric) for the procedural variants, from one subject in software rendering:

| Dimension | Baseline mesh | TRELLIS mesh |
|---|---|---|
| Identity/appearance | 3 | 3–4 |
| Anatomy | 3 | 3 |
| Deformation | 3 | 3 |
| Motion naturalness | 2–3 | 2–3 |
| Gameplay readability | 3 | 3 |

## Slice B: alternative image-to-mesh reconstruction

An isolated environment ran **TRELLIS-image-large** (Microsoft; MIT code and weights, DINOv2 encoder Apache-2.0). It used code commit `193e0502b5cb`, weights revision `25e0d31ffbebe4b5a97464dd851910efc3002d96`, Python 3.11.15, torch 2.5.0+cu124 and prebuilt wheels only (no `nvcc` on the host). The input was the same Shiba image. The GPU validation lock was held throughout, and the owner's app and model caches were untouched.

Candidates not run:
- **TRELLIS.2:** needs at least 24 GB and compiled extensions.
- **Hunyuan3D-2mini/2.1:** territorial licence exclusions, and its texture stage needs about 21 GB.
- **TripoSG:** no colour.
- **SF3D/SPAR3D:** Stability community licence and compiled extensions.

### Memory and timing

The stock pipeline does not fit the budget. It peaked at 15,948 MiB allocated and finished only because WSL2 spilled into host memory; with a 9.5 GiB cap it ran out of memory at FlexiCubes surface extraction. Keeping one stage network on the GPU at a time and running the 256³ surface extraction on the CPU (same algorithm) fixed this. The main run (seed 42, the pipeline's default 25 steps per stage, cfg 5.0) then peaked at 3,966 MiB PyTorch allocated and 4,434 MiB reserved, adding about 4.6 GB on nvidia-smi.

| Phase | Seconds |
|---|---:|
| Weights load | 15.2 |
| Image encoding | 0.65 |
| Sparse structure (shape) | 13.4 |
| Structured latent (shape and colour) | 6.8 |
| Mesh decode with colour | 9.3 |

### Geometry and appearance

Result:
- **Mesh:** 104,381 vertices and 208,758 triangles in one watertight component, with vertex colours.
- **Legs:** horizontal slices at 5–35% of height show exactly four clean leg sections. The baseline mesh has four plus 1–5 spurious loops per slice, and fragments into 19 pieces at 40% height.
- **Appearance:** cleaner ears, tail and paws. Colour is closer to the input, without the baseline's baked dark shading. The unseen far side and a white belly and tail underside are plausible inventions.
- **Seeds:** 42, 1 and 7 all give four separate legs, a curled tail and upright ears.

Caveats:
- **Background removal.** TRELLIS's default background removal cut out part of the light-grey cheek, which became a dark facial band on every seed. Flood-filling the pure-white background fixed it, so input matting needs its own review step.
- **Inner shell.** The raw output contains an inner duplicate shell. The official cleanup needs nvdiffrast, which could not be built here, so a voxel cavity test removed it and two tiny holes (7 and 6 edges) were closed. That cleanup failed on seed 1, where the inner shell opens to the outside. A robust cleanup, or a build of the official one, is a prerequisite.
- **Untested setup.** The official texture-baking path was not tested.
- **Favourable input.** The input is a render of a low-poly authored asset, which may favour TRELLIS more than real photos would.

Scripts, logs, environment and receipts are retained privately under the ignored `.local/slice-b` directory (16 GB including the environment and model cache). The scripts are not committed because they include local workarounds that have not been reviewed: an xformers import alias, and DINOv2 weights converted from Hugging Face because the official download host currently serves an expired TLS certificate. TLS verification was not bypassed.

## Recommendations

1. **Adopt per-family template rigs as the M5 baseline.** Keep UniRig as an optional comparison rather than the path to playable characters. The template removes semantic mapping and retargeting from the critical path, so authored or procedural motion works for every character of the family. M5's semantic-mapping and correction scope shrinks to template-fit review and correction.
2. **Run a bounded M4 reconstruction comparison on the frozen development corpus before integrating Idol stages further.** Compare TRELLIS-image-large (with the low-memory changes, robust shell cleanup and reviewed matting) against the current route on photos, drawings and renders, then make a go/no-go on replacing the stereo route as the default mesh source. Idol splats can remain as the visual reference. #68's durable-stage plumbing still applies to whichever backend wins, but should not lock in the stereo route first.
3. **Treat motion as its own decision (M6).** The stylized Fox clip is not a dog walk. The procedural gait plus IK passes the numeric gates, but it needs a reviewed motion source or a tuned procedural profile, plus idle and turn clips, before it can pass natural-motion review.
4. **Before any acceptance claim:**
   - Owner visual review of these frames and the playable samples.
   - A hardware-rendering benchmark.
   - The front-leg elbow check.
   - Running the fit across the frozen development corpus, with `AnatomyError` cases routed to manual review.

## Limits of this evidence

- **Scope:** one development subject (already exposed in development) and one template family. No held-out exposure and no success rate.
- **Heuristics:** the landmark heuristics assume four separable floor contacts, an upright standing pose and a tail reachable from the back. They will reject or mis-fit some inputs: sitting or occluded dogs, long hair, and fused or tucked legs.
- **Motion coverage:** only a walk exists (no idle, trot, run or turns).
- **Not tested:** hardware performance, FBX/Blender export round-trips, durable-pipeline or API integration, and the owner's review.
