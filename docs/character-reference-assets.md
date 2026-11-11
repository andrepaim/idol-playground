# Character reference assets: source conversion receipt

This is a partial [M0](image-to-playable-milestones.md#m0--baseline-scope-and-decision-freeze) source-validation receipt, following the [development baseline](character-baseline.md). It does not complete M0 or establish a new image-to-playable result. Repository runtime remains unchanged from `5f628ab60c104e3bf67d0bc798627d8c925ccf11`; the experiments below use private, isolated tooling and source assets. Original downloads, failed attempts, converted assets and detailed logs remain local and are excluded from commits and CI artifacts.

## Native Blender diagnosis

Earlier exports through the installed Python `bpy` 4.2 module wrote some files but exited with signal 11. Those files were not accepted as successful conversions. The official Blender application provides a separate successful route; this is evidence for that invocation, rather than a diagnosed fix for Python-module shutdown.

The [official Blender 4.2 release directory](https://download.blender.org/release/Blender4.2/) supplies `blender-4.2.0-linux-x64.tar.xz` and its SHA-256 manifest. The downloaded archive is 352,269,932 bytes, with SHA-256 `4f4fd7646af01f6fee9d420408318381a6e52571268eb7cf9cd5033bd9e7a359`. Native Blender reports version 4.2.0, build `a51f293548ad`.

The archive was checksum-verified before execution and extracted into a new ignored prefix. Validation bounded entry count and expanded sizes, rejected absolute/traversal paths and special files, and constrained links to the archive's top-level directory before applying Python's `data` extraction filter. An initial stricter check refused the archive's internal library links before extraction; the successful check explicitly validated all 82 internal links among 6,478 entries. No working Python/GPU environment, model cache or global installation was replaced.

Each native process used private user config/scripts/data directories and this invocation shape:

```sh
blender --background --factory-startup --disable-autoexec --threads 2 \
  --python-exit-code 1 --python trusted_conversion_script.py
```

The trusted script opened source files with `use_scripts=False, load_ui=False`. `CUDA_VISIBLE_DEVICES` was empty and no model inference ran. A minimal authored cube/armature export/reimport, both actual swimmer source conversions, and the final round-trip geometry check exited normally with status 0. No forced process exit or UI quit operator was used. These are CPU source-conversion checks, not CUDA lifecycle evidence.

## Swimmer sources and conversions

| Subject | Primary source / rights | Accepted source route | Structural result |
|---|---|---|---|
| Shark | [Quaternius animated fish](https://opengameart.org/content/animated-fish), CC0 1.0; included license retained | Original `Shark.blend` → native Blender → GLB | 72,304 bytes, 1 skin, 8 joints, 1,226 exported vertex records, 644 triangles, `Swim` clip |
| Cartoon fish | [joyfulsquirrel fish](https://opengameart.org/content/fish-1), CC0 1.0 as stated on the primary asset page | Original `fish.blend` plus supplied `fish.png` → native Blender → GLB | 33,688 bytes, 1 skin, 5 joints, 339 exported vertex records, 328 triangles, `swim` and `tpose` clips |
| Barramundi | [Pinned Khronos sample](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/8f492390ddc7a2ae221a1369ef560589cf8c70fb/Models/BarramundiFish), CC0 1.0; README credits Microsoft | Original self-contained GLB; no conversion | 12,488,144 bytes; static source, without skin or animation |

The Shark route uses the original Blender source, whose two material colors already have alpha 1. The earlier FBX derivative's zero-alpha masked materials are not reused or silently repaired. Native export retains the source's opaque diffuse values. The 8-joint original Blender rig and earlier 12-joint FBX-derived rig are distinct representations and are not interchangeable evidence.

The cartoon fish's embedded PNG is byte-identical to the supplied source texture: SHA-256 `bbf055219b4daa3770ae2e605015d14e0e5c1e28c63943456b1afc5d82b3b368`. Neither source required guessed texture content or an appearance repair. The older Scardinius candidate remains excluded from this selection; its legacy material interpretation is unresolved.

Independent binary/accessor inspection checked GLB lengths, self-contained buffers, finite values, hierarchy cycles/parents, invertible inverse-bind matrices, triangle indices, nonnegative normalized weights, valid joint indices and monotonic animation times. Both converted swimmers have at most four weight slots, no unbound vertices and no degenerate triangles. Maximum weight-sum error is `1.20e-7` for Shark and zero for the cartoon fish.

Native source/reimport checks compared evaluated character meshes at frame 1 with matching source actions. Both retain their triangle count. Maximum bounding-coordinate error divided by source extent is `1.21e-7` for Shark and `4.50e-8` for the cartoon fish. Initial diagnostic attempts accidentally included Blender's imported `Icosphere` bone-display helper; another comparison selected different actions. Those attempts are retained, and the final check explicitly selects armature-modified character meshes and matching actions. Raw `bpy.data.objects` counts must not be treated as exported character geometry.

| Artifact | SHA-256 |
|---|---|
| Original Shark Blender source | `fb40d53563a537bd1540fff6e3603365d702888be47e21c15c2c16815e8474f5` |
| Native Shark GLB | `2742240dc68fc6a666c0750642ffa448861f0e4875d0ac2c40f9e867349275d0` |
| Original cartoon-fish Blender source | `a09d86dee8e0ea94f25d18e1d55a63c828ab0c7b4d1eed0547b121edf0ec277e` |
| Native cartoon-fish GLB | `85d27367b39130a3f3a2422cfba7471db22e19a21b8ee6a51d8c2c17502f9d82` |
| Original Barramundi GLB | `ecc3bafb6b00f2c8b810863c388e3768a7b7ea0d0335e8cb8c574c266e571f4a` |

## Source appearance review and frozen subjects

Chromium 158.0.8127.18 with Three.js 0.187.0 and SwiftShader rendered local source assets at 512 × 512, DPR 1, on a white background. Network routing allowed only local fixture/model/library bytes; browser page errors were absent. The review covered 58 frames: two views at 0%, 25%, 50% and 75% of each authored animation, plus two static Barramundi views. All five subjects below were visually inspected. The fish remained visible with retained colors/textures; sampled articulated parts stayed attached without catastrophic collapse. This limited sampling does not measure loop continuity, contact, natural motion or hardware performance.

Three rendered swimmer subjects were frozen at `2026-11-11T23:37:56.629543+00:00`, before any model inference on those subjects:

| Subject | Split | Rendered PNG SHA-256 |
|---|---|---|
| Shark | Development | `44833ab40e3f5d76e1c00fc75e1dbbb28a11249b1d895f030a2e82b85e7d4aec` |
| Cartoon fish | Development | `459ca81e4216c7d64af9095ffcc06159679609964266050bbf851029836ccae6` |
| Barramundi | Held-out | `63378f296fbbcc88273b7c3904b8ac5e1586dfacffddae36d8f3b514c2b0d873` |

Shark was designated a development rig reference before the split. Of the remaining two images, the lower image hash selects development and the higher selects held-out. This choice is recorded before model evaluation and must not change in response to model results. Earlier drawing/photo/land-render subsets and their splits remain intact, bringing the frozen population-image subjects to 27: nine drawings, nine photos and nine renders. Barramundi's held-out designation permits source/provenance review, not subsequent development tuning.

The active private swimmer manifest is `swimmer-render-subset-frozen-v2.json`, SHA-256 `5a9bbb9c95773edaab32ba6d328204d02238107f7f4f49ab539a20fce0c742cc`. Its predecessor, SHA-256 `aef77dd98295a9be14d3bd602541e0f081cf157ca67f6e1418390d1cb953411c`, remains preserved. The metadata-only revision removes an unsupported “scanned” description and adds the Barramundi README's exact author credit; subjects, pixels and splits are identical, with no intervening model inference.

Shared source ancestry remains explicit. Quaternius also authored the land canine pack, and the Khronos collection supplies several other subjects. Different named subjects are useful engineering coverage, but do not establish statistical independence or absence from model pretraining.

## Authored rig references

Three development references now have independent structure/weight checks and sampled authored-animation review. They are references for future validators and retargeting, outside the image-quality population denominator.

| Reference | Rights and source | Validated source structure | Review limit |
|---|---|---|---|
| RiggedFigure | [Pinned Khronos source](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/8f492390ddc7a2ae221a1369ef560589cf8c70fb/Models/RiggedFigure), Cesium, CC-BY 4.0 | 19 joints, 370 vertex records, 256 triangles, one clip | Stylized biped articulation; no natural walking/contact acceptance |
| Fox | [Pinned Khronos source](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/8f492390ddc7a2ae221a1369ef560589cf8c70fb/Models/Fox); PixelMannen model CC0; tomkranis rig/animation and AsoboStudio/scurest conversion CC-BY 4.0 | 24 joints, 1,728 vertex records, 576 triangles; `Survey`, `Walk`, `Run` | Canine-like proportions; does not validate the legacy fixed canine mapping or generic retargeting |
| Shark | Original authored source and native conversion above, Quaternius, CC0 1.0 | 8 joints, 644 triangles, `Swim` | Swimmer reference; no axial-profile limits, fin control or motion-quality acceptance |

All three have finite inspected accessors, valid indices/hierarchy, invertible inverse-bind matrices, four weight slots, normalized nonnegative weights, zero unbound vertices and zero degenerate triangles. The private reference index has SHA-256 `57cfc0f5fdb180db0e556d21b30009930c11da99a6cb70b9089ebaeeef4811f1`. Forty of the 58 reviewed frames cover these three references. They are accepted only as structural and sampled-animation source references; semantic-role annotations, contact metrics, full deformation probes and generalized mapping remain M5/M6/M9 work. Held-out CesiumMan and Husky were not used for these development checks.

## Remaining gates

M0 remains open. Six named adversarial cases, complete per-stage/resource accounting, the agreed quality rubric and independent/owner visual acceptance remain outstanding. The 27 frozen population inputs have not established a success rate. The earlier generated canine still fails the game-mesh budget and the current fixed walking-profile mapping, as recorded in the development baseline.

This increment changes documentation only. CPU source conversion and software-rendered browser inspection establish neither reconstruction/model quality nor CUDA cleanup, GPU memory, hardware rendering performance or playable-character acceptance. No runtime adapter, provider, release, asset publication or owner-data migration is enabled.
