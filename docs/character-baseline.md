# Character source review and development baseline

This is partial M0 evidence. It does not complete the [corpus or tier acceptance](image-to-playable-validation.md). Raw source images, downloaded models, generated assets and private review files remain in ignored local directories.

## Source review

The [Quaternius Ultimate Animated Animals pack](https://quaternius.com/packs/ultimateanimatedanimals.html) supplies an independently authored source for a canine development experiment. The author's free download links to a public folder containing the July 2021 pack and its license. The included license explicitly dedicates the models under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). No paid source kit or account change was used.

Four embedded glTF 2 assets were acquired and hashed. All have finite position data and twelve animation clips. Distinct file/normalized-position hashes distinguish their geometry, but do not prove independent subject ancestry. Their placement into a development/held-out corpus remains unfrozen.

| Source | Bytes | SHA-256 |
|---|---:|---|
| Wolf.gltf | 3,175,890 | `cc02e9d128b5715f352ee8bea086f97a35f1d875d240de99b0f9f2775c37d415` |
| Husky.gltf | 3,059,335 | `0cfd85ddfcc5c07caf1bdeb296b21017b0da4c8558a92086daf4a172e0bf8d97` |
| ShibaInu.gltf | 2,894,445 | `3236979b94a840eb72d9ce091b1361da327a96f5ce068e666680297480f30f6b` |
| Fox.gltf | 3,163,174 | `2f36e3c9c75ecddda85c5f9944e98ee1e88e7c679a546534aff1cea8ecde64c7` |

Eight actual source views were reviewed: the four models have complete framed bodies. Source review used Chromium 158.0.8127.18, Three.js 0.187.0 and SwiftShader at 512×512. This establishes the inspected renderer/source appearance, without a hardware rendering claim. Shiba's front three-quarter view is explicitly a development input from this point onward; it cannot later become an untouched held-out subject.

A separate direct-accessor/transform inspection of Shiba found 3,966 vertices, 1,950 triangles, 46 joints, at most four weight slots, no unbound vertices or degenerate triangles, and maximum weight-sum error `1.20e-7`. Its initial scene pose differs from the inverse-bind pose: the largest per-primitive normalized displacement is about 0.11. This is a diagnostic, not proof of an invalid rig; a posed scene need not equal its bind pose. Bind-pose interpretation, anatomical roles, contact and deformation/animation review remain required before accepting it as an authored runtime baseline.

## Photo candidates and exclusions

The [Open Images download documentation](https://storage.googleapis.com/openimages/web/download_v7.html) and [official dataset repository](https://github.com/openimages/dataset) provide per-image provenance/license fields; annotation licensing does not grant image rights. Nine candidates were acquired from the public CVDF validation image store with permanent source/landing URLs, reported author/license, actual downloaded-image SHA-256, dimensions and acquisition time. Downloaded bytes can differ from the original image metadata because dataset copies may be transformed; their hashes are recorded separately.

The browser reader could not access the original Flickr pages, but bounded direct HTML reads subsequently worked. Across fifteen metadata candidates, thirteen primary pages' `ImageObject` records matched the permanent landing URL and reported CC-BY 2.0; two pages returned 404 and were not retried. The HTML content hashes and per-image attribution are retained. Fourteen photos were acquired in total, including one whose primary page is unavailable; that source remains provisional. The images are not committed, exported or accepted corpus cases. Any permitted redistribution must retain attribution and applicable license terms.

Visual review found discrepancies with the dataset's composition/anatomy labels. A lying dog with concealed hind limbs, a snow-obscured dog and a sitting dog were excluded from the core canine set. A nudibranch labeled as fish was excluded from the fish/shark support envelope, and a camouflaged bottom-dweller was excluded from the initial clear-silhouette set. Other photos include difficult overlapping legs, concealed upper-leg anatomy, far-side canine occlusion and complex fins. These limitations are recorded per candidate before model evaluation. No photo model evaluation or split freeze has occurred.

Earlier Wikimedia image downloads returned HTTP 429; alternative photo hosts returned HTTP 500. Those unchanged failures were not repeatedly retried. Public metadata availability does not establish a usable, reviewed image corpus.

## Frozen drawing subset

Nine independently authored drawing candidates were selected from [OpenMoji](https://github.com/hfg-gmuend/openmoji) and [Noto Emoji](https://github.com/googlefonts/noto-emoji). OpenMoji source revision `3e01de523ddefe9c5e46a7765b15efef04bf9002` includes its CC-BY-SA 4.0 license and per-artwork author metadata. Current Noto's README image-license claim conflicts with its root OFL license. The initial selection was withdrawn before inference; the original manifest and images are preserved. Actual historical artwork was instead acquired from revision `41e31b110b4eb929dffb410264694a06205b7ad7`, whose included LICENSE explicitly contains Apache 2.0, SHA-256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`. All three historical source images were rerendered and reviewed; the license was not substituted onto current artwork. Original SVG hashes, exact source URLs, credits and license files are retained locally.

The selected subjects are a standing human pictogram, two visibly distinct clothed dancers, three distinct dogs including a poodle, and three distinct fish. Source review excluded two head/torso-only characters and a close dancing variant of the selected standing pictogram before inference. The source drawings are shared-library artwork, with that relationship recorded; they are separate authored subjects rather than the parameter variants in the procedural probe set.

SVGs were checked for scripts/external references and rasterized at 512×512 over white using Chromium 158.0.8127.18 with network requests blocked. Visual review annotated concealed limbs, disconnected pictogram head, unusual proportions and unseen depth. These are expected review conditions, not assurances of reconstruction success.

At 2026-11-11 19:51:33 UTC the revised drawing subset was frozen with two development and one held-out subject per family. Sorting each family's rendered-image SHA-256 selects the third as held-out, before any model evaluation. The active private manifest has SHA-256 `efc204eab148b33bba89b55522c12610f1cd319f78736f1f51ecc8eb821b2beb`. All nine drawings remain unevaluated. Neither the initial nor revised split saw model outputs. This freezes only the drawing subset; photos, independent renders, adversarial fixtures and accepted authored rigs remain incomplete. Original sources and derivatives are retained locally; no artwork or generated model is published by this documentation increment.

## Development reconstruction

The isolated Shiba experiment uses existing runtime revision `c8047423a36e69a1b31708a7ee300481b1d53a52`. All tracked runtime files match that revision. The reconstruction receipt records `dirty=true` solely because its local `node_modules` dependency symlink is untracked; the subsequent rig run also has this untracked documentation draft. Runtime source hashes and the exact Git status are retained. This is disclosed exploratory evidence, not a claim of a clean complete tier-acceptance run.

Input SHA-256: `2d677c6855fb3d6dfd654586eea5b643025f2b0cf091852c3c3bcd810757efdb`. The 512×512 PNG renders the author's neutral scene; its camera, source hash and renderer receipt are retained locally. Baseline settings: synthetic mode, 50 Idol steps, 262,144 Gaussians, seed 42, guidance 3.0 and time rescale 3.0, followed by 36 stereo pairs, ten DLNR iterations, 0.002 fine voxel and largest component. No held-out model output was used to choose these settings.

The runner reserves the local GPU validation lock, verifies both legacy and character jobs are idle, temporarily stops only the identified local app, runs bounded isolated workers against existing offline caches, and restores the app. Original owner outputs and source assets are preserved. Phase logs, process-tree RSS samples, outputs and receipt remain private. Sampled process-tree RSS can include shared pages and is not total system memory; PyTorch allocated peaks are not total device memory.

Actual RTX 3060, driver 610.88, 12,288 MiB, 2026-11-11 UTC:

| Phase | Wall seconds, including worker startup | Sampled process-tree RSS MiB | Peak PyTorch allocated MiB |
|---|---:|---:|---:|
| Idol | 148.309 | 2,966 | 5,094 |
| Calibrated software capture | 283.246 | 1,289 | Not a CUDA phase |
| DLNR stereo | 27.065 | 2,231 | 590 |
| Fine surface | 5.512 | 1,354 | Not measured |
| Mesh export | 1.004 | 369 | Not measured |
| Rig geometry preparation | 23.048 | 1,081 | Not measured |
| Skeleton prediction | 22.549 | 3,958 | 3,999 |
| Skeleton geometry extraction | 3.009 | 578 | Not measured |
| Skin prediction | 24.557 | 6,570 | 4,207 |
| Rig export | 53.114 | 1,540 | Not measured |
| Three-format reimport verification | 10.023 | 1,207 | Not measured |

Idol uses PyTorch 2.15.0+cu132/CUDA 13.2; stereo and rigging use their existing isolated PyTorch 2.5.1+cu124 environments. All workers exited successfully. Model pins remain those in [mesh generation](mesh-generation.md) and [rigging](automatic-rigging.md). The PLY has exactly 262,144 records with all seventeen float properties finite. Splat SHA-256: `ced73ca8778b0a50a90a9de5c631d486d71f25a7766ff25b5951062de2857434`.

Reconstruction workers total 465.136 seconds; rig workers total 136.300 seconds, excluding the separate visual/silhouette analysis and the pause between experiments. The colored mesh has 428,219 vertices and 855,576 triangles; 33,686 fragment triangles were removed. It is not watertight. Mesh GLB is 29,110,180 bytes; rig GLB is 34,282,424 bytes. After diagnostic review outputs, retained mesh and rig working folders occupy about 322 MB and 202 MB respectively. These are observed files for one attempt, not installation/storage admission limits or ceilings.

Eight extra camera angles, excluded from the reconstruction cameras, give mean mesh-to-splat silhouette IoU 0.97164 and minimum 0.96687. Both all-eight-angle inspection and the prepared-source comparison show retained colors, recognizable appearance and four leg silhouettes. This measures agreement with a generated splat, not unseen real anatomy or dense-to-prepared simplification quality. Surface roughness and holes remain visible. The mesh exceeds the 100,000-triangle runtime maximum by more than eight times, so it fails preparation acceptance.

UniRig produced 32 bones, normalized skinning and a diagnostic bend. Direct generated-GLB accessor checks found no unbound vertices, at most four influences, finite nonnegative weights and maximum weight-sum error `1.20e-7`. GLB, FBX and Blender reimports retained all 428,219 vertices, the bone count and vertex colors. Three camera views of neutral/bend/skeleton overlays rendered without browser errors. The bend shows a localized ragged neck/chest crease that needs investigation; this single generic bend cannot pass the profile deformation suite. Semantics, full joint probes, contact, natural motion and gameplay remain untested.

The existing `canine-34-v1` walking boundary correctly reports this 32-bone rig as unsupported. No walk was generated and no known-asset mapping was forced onto it. This is direct evidence that semantic rig mapping is required for new generated subjects. The development result is **not playable and not accepted end-to-end**. Source/quality self-review is separate from the owner's subjective product acceptance.

The owner's app was restored after both experiments, with character input/manual assessment enabled, no active legacy job and no loaded Idol model. No owner character or output was created by the baseline.

## Remaining M0 gates

The full 18 land images, nine swimmer images, six adversarial cases and three accepted authored rigs still need complete provenance, subject independence review, annotations and a frozen split. Only the nine drawing cases are frozen so far. The separately generated [development probes](character-probes.md) do not replace those subjects. End-to-end stage/resource measurements and quality accounting remain incomplete. M0 and all broader image-to-playable quality tiers stay open.
