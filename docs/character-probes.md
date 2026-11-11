# Procedural character development probes

`experiments/characters/prepare_fixtures.py` generates first-party drawings and rendered static geometry for isolated development checks. It does not assemble the independent roadmap corpus, create accepted authored rigs, or establish reconstruction/anatomy quality. See [acceptance requirements](image-to-playable-validation.md).

Use the existing locked CPU development environment, installed frontend dependencies and Chromium:

```sh
npm ci --ignore-scripts
.venv-check/bin/python experiments/characters/prepare_fixtures.py --name my-character-probe-run
```

The script writes a new ignored `.local/NAME` and refuses any existing directory, including a partial attempt. It does not install packages, download models, use owner inputs, call an image API or overwrite previous outputs. Keep each run for inspection. A safe generated name is required; the loopback server serves only the known fixture code and Three.js files, with resolved-path containment checks.

The set has 18 PNGs: biped/quadruped/swimmer × drawing/render × three parameter variants. Each drawing retains SVG source; each render retains a static self-contained GLB, bounds and authored geometric anchors. These anchors are not anatomical ground truth or a skin/skeleton validation. Subjects share a generator and the variants are close relatives; do not count them as the required independently sourced subjects or a population-quality denominator. A `held-out-probe` label isolates development parameters only and is not a held-out subject evaluation.

The manifest records source hashes, base Git revision/dirty status, Python/Pillow/Three/Chromium versions, actual renderer, dimensions, asset hashes and limitations. Forced SwiftShader supports local software rendering; it supplies no CUDA or hardware-performance evidence. `review.html` provides a contact-sheet view for visual inspection. No raster/model output is committed or distributed by this tooling.

Generation is visual/exploratory work: concrete acceptance consists of a real new export, PNG dimensions and hashes, parsable self-contained GLBs, inspected silhouettes and no-overwrite behavior preserving an existing manifest hash. A test that merely repeats drawing coordinates would add no useful evidence. Relevant repository checks and combined CI still apply. This increment preserves the separate corpus acquisition, source/license review, split freeze and actual RTX 3060 stage-baseline work in M0.

## Tooling receipt

Clean combined source revision `dab3d7f25475cb43c6531cb01d4e923ddf8e566a`, 2026-11-11 UTC: 18 actual 512×512 PNG exports and nine self-contained binary glTF 2 files passed source/image hash, dimensions, framed nonempty silhouette and embedded-resource checks. The contact sheet was inspected: complete framed bodies are visible. Python 3.11.15, Pillow 12.3.0, Three.js 0.187.0, Chromium 158.0.8127.18, forced SwiftShader. No inference or owner inputs were used.

Rerunning against the same directory failed with `FileExistsError` and preserved manifest SHA-256 `909def80c10fc1cf2b86a2262b91d2b79bfeec7534705c91dec115350e789683`. An unsafe output name was refused. Receipt and exports remain ignored in the corpus worktree. Repository lint/docs/whitespace, 177 Python tests, 33 infrastructure tests and seven controller tests pass. PR/combined CI remain required.

The independent corpus is still incomplete. Acquiring separately licensed assets does not make these close procedural variants independent subjects, and a static GLB is not an accepted authored rig. M0 remains open for provenance/split, actual stage measurements and quality assessment.
