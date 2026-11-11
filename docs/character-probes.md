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
