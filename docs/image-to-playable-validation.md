# Image to playable character: validation and acceptance

Status: proposed acceptance contract, 2026-11-11. Read with the [product/architecture plan](image-to-playable-plan.md) and [milestones](image-to-playable-milestones.md). No measurement below is a claim that the current system passes. Existing [validation policy](validation.md) and [AGENTS.md](../AGENTS.md) continue to apply.

## 1. Evidence levels and acceptance rules

Keep five evidence classes separate:

| Evidence | Establishes | Does not establish |
|---|---|---|
| Implementation review | Intended behavior, contracts and likely failure modes | Runtime correctness or model quality |
| Automated CPU tests | Tested logic, schemas, filesystem/API behavior | CUDA compatibility, inference quality or actual GPU cleanup |
| Browser automation | Tested browser flow, rendered output and input behavior | Real-hardware performance if the renderer is software |
| Actual GPU/worker runs | Tested loading, inference, lifecycle and resource behavior | General anatomy coverage or natural motion without visual assessment |
| Visual/model-quality review | Reviewed appearance, anatomy and motion on named cases | Untested populations, hardware or deployment environments |

A feature is accepted only when all required classes for its affected behavior pass. Record revision, environment, effective settings and limitations. Historical GPU evidence does not validate changed inference code. A successful export is not proof of playable quality. A visually convincing single example is not a corpus result.

Numbers below are proposed initial thresholds. M0 must freeze or explicitly revise them using development evidence before final evaluation; M1 freezes runtime-specific budgets before its acceptance run. Keep the original proposal and rationale in a decision log. Held-out failures cannot be fixed by silently lowering thresholds or removing difficult cases. If criteria change materially after held-out exposure, report that exposure and add fresh held-out cases before claiming a new unbiased evaluation.

Hard invariants such as data preservation, finite geometry, valid binding and no unauthorized external calls are not adjustable quality targets. Optional capabilities can be deferred visibly; required checks cannot be waived to merge an affected feature.

## 2. Corpus, provenance and coverage

Start with 36 assets across the full roadmap, of which only the relevant subset gates each tier:

| Group | Composition | Development / held-out | Purpose |
|---|---|---|---|
| Land images | 2 families × 3 styles × 3 distinct subjects = 18 | 12 / 6; two development and one held-out per family/style cell | Biped/humanoid and canine-like quadruped; photo, drawing, rendered image |
| Swimmer images | 1 family × 3 styles × 3 subjects = 9 | 6 / 3 | Fish/shark-like expansion |
| Adversarial inputs | 6 named failure cases | All regression fixtures | Robustness and honest rejection/review |
| Authored baseline rigs | Biped, quadruped, swimmer = 3 | All development fixtures | Isolate runtime/retargeting correctness from reconstruction |

The nine canine-like quadruped images are the T1 evaluation subset; M0 must select a canine-supported subset consistent with T1 scope, rather than silently including unsupported quadrupeds. Broader species require additional M8 cases and a revised coverage report. Keep pose, proportions, fur/clothing and stylization varied within the declared support envelope.

Adversarial cases cover cropped limbs, severe occlusion/overlap, multiple subjects, ambiguous anthropomorphic anatomy, unsupported topology/body plan, and malformed/oversized input. The ambiguous humanoid-animal case may legitimately succeed after review; the expected result is safe routing and explicit uncertainty, not automatic rejection of all adversarial inputs. Use separate generated malformed files for parser tests as needed.

For each asset record an ID, source/license, redistribution permission, content hash, privacy classification, expected body plan, visible/hidden anatomy, split, and expected review/rejection behavior. Never put personal photos, raw private outputs or model checkpoints in public fixtures/CI artifacts. Prefer authored/synthetic or reviewed public assets with documented provenance. Downloading a public asset does not itself establish redistribution rights.

Freeze subjects before evaluation. Avoid near-duplicate train/development/held-out images of the same subject or rig. Use held-out cases for final evaluation, not iterative parameter selection. Human reviewers must know which views are synthesized; they cannot verify unseen geometry against a single source image.

### Tier success proposals

| Tier | Proposed minimum acceptance |
|---|---|
| T0 known-asset proof | All mandatory gameplay scenarios on one reviewed canine; invalid-package fixtures fail cleanly |
| T1 canine image MVP | At least 8 of 9 canine images accepted end-to-end, including at least 2 of 3 held-out; at least 2 of 3 in each style; all failures recoverable/labeled |
| T2 land beta | At least 15 of 18 land images accepted, including at least 5 of 6 held-out; at least 2 of 3 in every family/style cell; no regression of T1's accepted support |
| T3 swimmers | At least 8 of 9 swimmer images accepted, including at least 2 of 3 held-out and 2 of 3 per style; land regression suite remains green |

An accepted case must meet every required geometry, rig, motion, runtime and packaging gate. Count generated failure, rejection, timeout and correction-limit exhaustion in the denominator for in-scope cases. Report automatic successes, successes after bounded correction, and failures separately. Proposed correction allowance: no more than ten minutes of supported review/correction per case and two downstream retries; report actual interventions and elapsed time. Blender sculpting or hand-rigging outside the supported UI does not count as automatic/product success.

These small samples are engineering release gates, not statistically reliable population accuracy estimates. Publish denominators and the support envelope, not an unsupported “works on any image” percentage. Extend the corpus whenever a new family, representation or recurring failure is introduced.

## 3. Stage quality gates

Let `L` be the diagonal length of the canonical prepared mesh's axis-aligned bounding box in its neutral pose. It must be finite and nonzero. Normalize geometry/contact metrics by `L` so small and large characters are comparable. Store physical scale separately; using a guessed scale must not change normalized pass/fail results.

### Input and anatomy routing

- Decoded image type/dimensions/size are validated before expensive work; invalid input has a bounded actionable response.
- Expected anatomy is compared with visible evidence; confidence alone cannot pass an anatomical check.
- Required profile is either correct, explicitly reviewed/corrected, or rejected. No known unsupported topology silently runs a supported-family animation.
- Model-assisted mode reports raw proposal accuracy, review rate, corrected accuracy, false confident routing, calls, latency and cost. Compare with deterministic/manual mode.
- All adversarial cases meet their specified safe outcome. Text in an image cannot change tool permissions or trigger code execution.

### Reconstruction and mesh preparation

| Check | Proposed gate | Method/limitation |
|---|---|---|
| Geometry validity | Finite positions/normals, valid indices, no zero-area export triangles, nonzero bounds | Deterministic validator; internal raw source may retain diagnosed defects |
| Required anatomy | All required limb/body chains visibly represented and separable enough to articulate | Multi-view human review plus geometric diagnostics; absence of hidden ground truth disclosed |
| Canonical coordinates | Documented axes/units/origin; transform round-trip error ≤ `1e-5 × L` | Synthetic transform fixtures and exported vertices |
| Triangle budget | Target ≤50,000; initial maximum 100,000 per playable character | Dense source retained; exceeding maximum blocks default runtime tier until budget is revised at its gate |
| Appearance | Visual rubric passes; no missing colors/textures or obvious bake seams | Compare source view, dense mesh and prepared mesh under matched lighting |
| Simplification silhouette | Mean foreground-mask IoU ≥0.95 over eight fixed canonical views against dense mesh | Detects preparation regressions only; cannot certify the dense mesh's correctness |
| Components/topology | No unexplained floating debris or fused required limbs; defects near bending joints reviewed | A globally watertight mesh is not an absolute requirement for open accessories |
| Materials/export | Self-contained required resources; no broken texture references | Reimport and browser rendering |

The prepared-mesh budget applies from T1 onward. T0 may use the existing dense canine to isolate gameplay; record its actual size and performance and explicitly leave mesh-preparation acceptance untested. An authored lightweight runtime fixture can isolate controller performance, but cannot replace generated-asset acceptance.

If silhouette and appearance pass but deformation fails, preparation is not accepted. Joint-region topology receives its final gate with the M5 deformation suite. Preserve source-to-derived transformation and vertex/weight-transfer provenance.

### Skeleton and skin

- Joint graph is acyclic, indices are valid, and required roles map to existing joints without incompatible duplicate assignments.
- Joint and bind transforms are finite; inverse bind matrices are nonsingular and consistent with the exported rest pose.
- Skin weights are finite, nonnegative and normalized within `1e-4` per vertex, with at most four active influences for the initial runtime profile. No required body region is unbound.
- Left/right and fore/hind roles are checked against geometry and reviewer-confirmed orientation. Missing joints and implausible chain lengths block the relevant motion.
- Run profile-specific neutral, flexion/extension, limb-lift and turn probes. No detached limb, visible cross-limb dragging, inverted knee/elbow motion, collapsed torso or major appearance loss may pass.
- Reimport GLB, FBX and Blender outputs when their shared export path changes. Compare pose/skin/materials and relevant animation transforms; record format-specific limitations.
- Compare generated rigs against authored valid/invalid fixtures to test the validator itself. Do not accept a validator that merely reproduces the generator's assumptions.

Joint-angle limits and interior-distance tolerances are body-specific and must be frozen in M5's profile definition. Avoid universal human angle limits for dogs or swimmers.

### Land motion

Measure at a fixed sample rate of at least 60 Hz over three consecutive cycles and over transitions; record the render/animation sampling method. Define contact regions and stance intervals independently of the error being measured, using reviewed mappings/clip annotations.

| Check | Proposed gate |
|---|---|
| Stance sliding | Maximum horizontal displacement of each reviewed contact point during an uninterrupted stance ≤ `0.02 × L` |
| Ground penetration | Maximum penetration of reviewed contact regions ≤ `0.005 × L`, excluding explicitly documented soft-surface effects (none in the initial scene) |
| Loop position seam | Maximum world-aligned endpoint mismatch of required joints ≤ `0.005 × L` after removing intentional root travel |
| Loop orientation seam | Required joint quaternion angular mismatch ≤5 degrees at the cycle boundary |
| Translation consistency | In-place clips have no unintended accumulating root travel; forward exports match their declared movement mode |
| Transition quality | Idle/walk/run transitions have no teleport, major pose snap or indefinite stale action; profile-specific acceleration stays within tested range |
| Natural motion | Visual rubric passes from front, side, rear and three-quarter views at normal and slow playback |

Contact bounds alone do not prove realism. A mathematically planted paw with a backward-bending leg is a failure. Record gait sequence, stance proportion, pelvis/torso motion, leg articulation and tail behavior in the visual report. Verify runtime playback-speed changes and actual movement speeds together; a clip that passes in Blender can slide when driven by the browser controller.

### Swimmer motion

Replace ground-contact tests with axial continuity, tail/body deformation, loop continuity, bounded turn curvature and depth behavior. No visible chain discontinuity, detached fin, collapsing cross-section or sudden heading jump may pass. M9 freezes species/profile-specific amplitude/frequency and turn-rate limits using development references before held-out evaluation. Land-contact metrics are not meaningful swimmer acceptance evidence.

## 4. Visual assessment rubric

Score identity/appearance, anatomical plausibility, deformation, motion naturalness and gameplay readability separately on a 0–4 scale:

| Score | Meaning |
|---|---|
| 0 | Missing/unusable result or critical structural failure |
| 1 | Major defects dominate the result |
| 2 | Recognizable but distracting defects make ordinary play unsuitable |
| 3 | Usable within the declared experimental scope; minor defects documented |
| 4 | Convincing within the tested views/motion and intended scope |

Proposed pass: every required dimension scores at least 3, with no critical defect. Static/rig-only experiments mark inapplicable motion/gameplay dimensions as untested, not passed. Review clips use matched camera/light/background, a source-image comparison, neutral orbit, deformation probes and actual gameplay. Save private evidence locally; publish only permitted sanitized samples.

Where possible, use a second reviewer and randomize candidate order. Record reviewers and disagreements. If only a coding-agent/self-review occurred, explicitly record that limitation and obtain the product owner's quality decision before asserting subjective product acceptance. Automated image comparison can assist but does not replace visual/anatomy review.

## 5. Runtime and package acceptance

Initial target: desktop Chromium on actual hardware, 1920×1080 viewport, device pixel ratio capped at 1 for the benchmark, one character, simple sample scene. Record browser/OS/GPU/driver, Three.js version, GLB hash, scene settings and whether WebGL uses hardware. Additional browsers/devices require their own support evidence.

Proposed runtime budgets to freeze in M1: median frame interval ≤16.7 ms and p95 ≤33.3 ms over a 60-second warmed run; default package GLB target ≤50 MB and maximum 100 MB; ≤40 draw calls for the default scene; textures ≤2048 per dimension unless an explicitly measured preset permits more. Report cold-load time, render/CPU timing where available, texture/geometry counts and resource usage separately. Frame intervals include browser scheduling effects and are not a direct GPU timing measurement. Do not claim a memory ceiling from incomplete browser instrumentation.

Mandatory scenarios:

1. Load accepted character and manifest; render correct color, scale, orientation, floor alignment and camera framing. Missing clips/resources/unsupported schemas produce useful errors.
2. Move cardinally and diagonally; verify normalized speed, acceleration/deceleration, turning, reset and camera-relative controls.
3. Compare a fixed-duration input script at 30/60/120 Hz simulation/render schedules; proposed end-position difference ≤1% of a nonzero scripted path length; test stationary input separately for zero drift. Handle a long frame/tab-resume without tunneling or teleporting.
4. Walk into walls, corners and obstacles; verify blocking/sliding and no visible ground penetration. Initial scene excludes slopes/stairs unless separately implemented and tested.
5. Repeatedly start/stop/turn and change speed; animation follows movement, including blocked motion. No double root movement, stuck walking, or visible pose snap.
6. Lose focus, open a modal, switch tabs and return; no held-key runaway. Input does not steal typing in authoring controls.
7. Replace/load/unload ten characters; event handlers, animation actions and GPU resources do not grow without bound. Use renderer resource counts plus actual-browser observation; disclose limits of memory measurement.
8. Verify existing static/rig/walk preview and turntable controls still work after visiting Play, including cleanup and restored playback state.
9. For swimmers, repeat movement/collision at top/bottom depth limits and during turns/ascents/descents.
10. Download the sample into a clean temporary directory; install locked dependencies, build and serve it using its instructions; run without the Python authoring backend, credentials or provider network access. State any initial network installation requirement clearly.

Package validation checks safe relative paths, hashes, manifest version, available clips, movement-mode consistency, finite controller values, asset/license inventory and absence of private source images/absolute paths/secrets. Export only selected public-safe lineage. Optional Blender/FBX authoring downloads remain separate from the runtime package.

## 6. Lifecycle, compatibility and fault matrix

Use isolated temporary outputs and synthetic/disposable fixtures. Never crash, fill, delete or migrate owner state to prove recovery.

| Scenario | Required result | Evidence |
|---|---|---|
| Browser refresh during work | Reconnects to same job; no duplicate generation | API and browser test |
| Duplicate submit/retry | Idempotent result or explicit conflict; no duplicate GPU owner | Concurrent API test |
| Cancel during each expensive stage | Child tree exits/reaps before ownership release; prior committed outputs remain | Process test and real affected GPU stage |
| Server restart between stage writes | Published output accepted only with complete valid manifest; incomplete attempt marked interrupted | Filesystem fault test |
| Server restart with an old worker | Reconcile process-start identity; no conflicting new work or blind PID kill | Isolated actual process test |
| Conflicting local server | Explicit ownership conflict before inference/state mutation | Isolated startup test |
| Disk full/permission failure | Structured failure, no false success or corrupt committed output | Disposable filesystem/fault injection |
| Missing/corrupt artifact/hash | Block reuse, show repair/retry action, preserve remaining files | Artifact tests |
| Change image/mesh/profile/mapping | Correct dependent stages invalidated; unaffected upstream output reused | Dependency-graph tests |
| Missing model/offline setup | Accurate readiness and actionable setup message; no repeated surprise download | Setup test and actual environment check |
| Provider timeout/malformed response/budget exceeded | Bounded failure/review/manual fallback; no unrestricted execution or retry loop | Fake-provider and selected real-provider tests |
| Old completed job | Loads/downloads as before or reports unsupported version without rewriting files | Compatibility fixtures |
| Export fails after valid motion | Retry package stage without rerunning inference | API/integration test |
| User rejects correction | Preserve original artifact and record rejection; do not mark accepted | UI/state test |

Exercise GPU/model-loading changes on the actual RTX 3060, with effective CUDA/PyTorch/model settings and process ownership recorded. Measure peak allocated/reserved memory and process/device memory where available; distinguish them. Observe unload/retry behavior and any concurrent external GPU use. Historical or mocked cleanup does not prove current VRAM recovery.

For each changed inference path, run a cold model load, warmed run, cancellation where supported, failure/retry and normal completion. Run an end-to-end supported case after integration; broaden to the relevant corpus when reconstruction/rig/motion quality changes. Proposed initial authoring target is ≤30 minutes per standard case with ≤10 minutes manual correction; M0 must measure and set the actual timeout/resource envelope. Do not invent stage timeouts that kill valid slow work without evidence.

## 7. Validation by change type

| Change | Minimum checks beyond review/current-main integration |
|---|---|
| Documentation only | Accuracy, repository local links/anchors, `git diff --check`, repository-selected CI |
| Manifest/geometry/math | Meaningful TDD fixtures, malformed inputs, compatibility, relevant export/API tests |
| Storage/recovery/process | Isolated fault and lifecycle tests, API/browser reconnect, actual worker/GPU checks when affected |
| UI/controller/runtime | Unit tests for behavior, frontend lint/build, browser acceptance and hardware performance when claimed |
| Model/inference/setup/CUDA | Automated adapter/setup tests plus actual affected GPU loading/inference/cancellation/memory and quality evidence |
| Skin/motion/Blender export | Deformation/contact/round-trip checks, real backend execution, visual review, GPU checks when inference affected |
| Optional reasoning | Schema/adversarial/budget/fallback tests, annotated routing evaluation, actual configured provider evidence for provider claims |
| Integrated tier | Corpus, full image-to-play flow, recovery, clean sample, regression, hardware/browser and combined CI |

Use current repository commands from [development](development.md) and [validation](validation.md), including relevant Python, frontend and browser checks. Existing GPU smoke commands alone do not cover the new end-to-end pipeline. Add dedicated acceptance runners only when their implementation is authorized; no command named in this plan should be mistaken for an existing script.

## 8. Evidence receipt and final gate

Each milestone/PR receipt records:

- Issue/PR and tested Git revision; base/integration revision and whether subsequent changes affect the evidence.
- UTC run window, OS, CPU/RAM, GPU model/driver, CUDA/PyTorch, Python/Blender/Node/browser/renderer versions as relevant.
- Model/source/checkpoint revisions, seeds where supported, effective parameters, environment/cache state and concurrency ownership.
- Asset IDs/hashes/provenance and split; output hashes; stage outcomes, retries, interventions and timing/resource measurements.
- Automated/API/browser/GPU/visual results separately; metrics, reviewer identity, failures, skipped checks and limitations.
- Private evidence location and sanitized public summary; no credentials, personal assets or raw private logs in issues/CI.
- Acceptance decision, remaining blockers, next action and supported capability tier.

Before declaring a milestone complete: review combined changes, integrate current main, rerun affected checks, merge its authorized implementation PR and verify CI on the combined commit. A green PR check before integration is insufficient. Required failing/unavailable checks leave the implementation unmerged and the issue open. A small corpus limits support claims even when every check passes.

Before release: complete the selected tier and [release checklist](releases.md), with separate explicit publication authorization. The planning branch itself stays unmerged for review unless the user asks to integrate it.
