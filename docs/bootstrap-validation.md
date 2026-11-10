# Repository bootstrap acceptance

Implementation: [PR #9](https://github.com/andrepaim/idol-playground/pull/9), tracking [issue #1](https://github.com/andrepaim/idol-playground/issues/1). Public repository: [andrepaim/idol-playground](https://github.com/andrepaim/idol-playground).

## Scope and risk

The foundation adds reproducible development environments, commands, CI, history guards, documentation, repository policy/settings, and a feature backlog. It does not change `app.py`, `model_setup.py`, `progress.py`, or the browser's application code. The original assets remain local. GPU inference is additionally checked because bootstrap introduces a new diagnostic/smoke workflow.

CI routing and private-file guards were developed against failing regressions before implementation. A further regression caught model/output symlinks and arbitrary `.venv-*` directories; the guard and ignore rules now handle them.

## Recorded local checks

At clean revision `1554293ec16dd2491738298d15bece4fd994f510`:

- Fresh public clone: `make bootstrap check doctor` passed with Python 3.11.15, Node 22.23.1, and uv 0.12.3.
- The clone downloaded no model weights and created no `.venv` CUDA environment.
- 21 API/progress tests passed, including actual CPU PyTorch module hooks; no tests skipped.
- 29 infrastructure regressions passed, including complete diff routing, fail-closed aggregation, broken links, changed/deleted targets, history leaks, and PLY validation.
- Three real Chromium acceptance tests passed with synthetic API/PLY data and software WebGL, including downloads, retries, repeated viewer lifecycle, and mobile overflow.
- Production frontend build, Ruff, ESLint, Markdown link/anchor checks, whitespace, generated/private-data guard, and Gitleaks history scan passed.
- npm audit reported zero vulnerabilities after pinning patched minimatch 11.0.1 for ESLint tooling.

At `c09aa09`, the additional model/output symlink and isolated-environment regressions, all CPU tests, both linters, and history guards passed. Those changes affect repository hygiene, not inference behavior.

The API test client reports an upstream deprecation warning. CPU PyTorch reports that NumPy is absent from the minimal check profile; the tested tensor/module-hook operations still run successfully. The Three.js build emits a large-chunk advisory; the viewer is already loaded dynamically. These are not claims of model quality or browser/GPU performance.

## Real GPU check

Clean tested revision: `1554293ec16dd2491738298d15bece4fd994f510`.

| Property | Observed |
|---|---|
| Hardware | NVIDIA GeForce RTX 3060, 12 GB |
| Driver | 610.88 |
| PyTorch / CUDA | 2.15.0+cu132 / 13.2 |
| Input | Procedurally generated blue object on white |
| Settings | Synthetic, 10 steps, seed 42, 65,536 Gaussians, guidance 3, shift 3 |
| Result | 65,536 finite-position PLY records with valid binary lengths |
| Total generation | 44.6 s |
| PyTorch peak allocated memory | 5,094 MiB; not total GPU usage |
| Storage | Disposable temporary directory, removed after acceptance |

The idle owner server was stopped to release GPU memory and restarted after validation. The test used the existing pinned local model files and the original CUDA environment. No uploads, saved outputs, models, or owner state were removed. The smoke test does not establish reconstruction quality, character readiness, or animation/export support.

## Verified GitHub settings

- Public repository, Issues enabled, wiki disabled.
- Squash merging enabled; merge commits and rebase merging disabled; merged branches auto-delete.
- `main` protection requires PR integration, up-to-date `Required validation` from GitHub Actions, resolved conversations, and applies to admins.
- Force pushes and branch deletion disabled.
- CODEOWNERS identifies the solo maintainer. No impossible self-approval is required; author review is not independent approval.
- Secret scanning, push protection, dependency alerts, and automated security updates enabled.
- Four milestones and seven planned feature issues exist. Feature implementation remains unapproved by the bootstrap task.

The first hosted run passed all selected checks: [CI run 42837174755](https://github.com/andrepaim/idol-playground/actions/runs/42837174755). Subsequent PR checks and combined-main CI must pass before closing issue #1; the final tested commit/run are recorded there to avoid claiming that this document's own commit has already passed checks.

## Remaining limits

An optional GitHub Projects board was not created: the authenticated CLI token lacks `read:project` and project-write access. Repository issues and milestones supply tracking. The GitHub connector also lacks access to this newly created repository; authenticated CLI operations were used instead.

No source-code license has been selected, release published, cloud hosting provisioned, or character model installed. Public source availability does not relicense the model components. See [third-party notices](../THIRD_PARTY_NOTICES.md).
