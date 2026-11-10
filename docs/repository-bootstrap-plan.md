# Repository and development infrastructure plan

Status: implemented under issue #1; final integration is tracked in its PR. The user authorized execution and selected a public repository. The sections below retain the original plan; effective settings and acceptance are recorded in [bootstrap validation](bootstrap-validation.md). Character-model installation remains future work.

## Objective

Turn the existing local app into a reproducible GitHub project before implementing the [Game Character feature](game-character-plan.md). Preserve the working Idol workflow, local models, and generated results while introducing the engineering rules used by DistillPod.

Scope includes repository setup, agent instructions, developer commands, automated checks, repository settings, documentation, issue planning, and evidence for real-GPU validation. The application remains a local GPU web app; cloud hosting, paid inference, release publication, and a production telemetry service are separate decisions.

## Findings from the current workspace

- Source directory: `/home/andrepaim/src/idol-playground`.
- No Git repository or remote exists in that directory.
- The app uses FastAPI, Python, Vite, vanilla JavaScript, and Three.js.
- `pyproject.toml`, `uv.lock`, `package.json`, and `package-lock.json` exist.
- Existing API and progress tests cover validation, concurrency, artifacts, errors, persistence, and ETA instrumentation. Some progress tests require real PyTorch modules and currently use `importorskip`.
- Existing ignored directories include `.venv`, `node_modules`, `dist`, `models`, and `outputs`.
- There is no app-level `AGENTS.md`, GitHub Actions configuration, repository security guard, issue template, PR template, or documented fresh-clone acceptance protocol.
- The current environment has an authenticated GitHub CLI for `andrepaim`, including repository and workflow scopes. Repository-name availability, project-board access, and settings entitlements remain to be checked at execution time.
- Local models and results already exist and must be preserved. Infrastructure validation must not interrupt active generation jobs.

## 1. Repository identity and ownership

Selected repository: **`andrepaim/idol-playground`**, public, default branch `main`. Repository name and visibility remain user-selectable; a broader name may be preferable as character generation expands beyond Idol.

Keep the existing local directory during bootstrap. A GitHub name change does not require moving the running workspace or rewriting machine-local paths immediately.

Before creation:

1. Confirm the selected owner, name, and visibility, or apply the user's accepted defaults.
2. Check whether the target repository already exists. Reuse it only if its identity and contents match the intended project; never overwrite an unrelated repository.
3. Check Git identity and remote authentication without printing credential values.
4. Inspect the account's available repository protections and Actions allowance. Do not purchase an account upgrade or provision paid runners as part of bootstrap.

Create an empty repository with Issues enabled. Keep the wiki and Pages disabled unless a later requirement needs them. Prefer the GitHub connector where it supports an operation; use the authenticated `gh` CLI for repository/settings/project operations the connector does not expose.

The repository is public by explicit user instruction. A code license remains a user choice; do not assume MIT solely because some model dependencies use it. Record third-party notices separately from the app's eventual source-code license.

## 2. Carry over DistillPod's engineering rules

Source reviewed: `/home/andrepaim/src/distillpod/AGENTS.md`, plus its development, CI, and repository-security instructions. This local path is a provenance note, not a portable repository dependency. The new repository must contain its own complete policy and guidance.

Use [agents-policy-draft.md](agents-policy-draft.md) as the proposed root `AGENTS.md`. It is a draft until bootstrap installs it at the repository root.

| DistillPod rule | Application here |
|---|---|
| Plan before implementation | Behavior, acceptance, components, risks, steps, and validation required |
| Feature authorization covers completion | Carry authorized implementation through PR merge and combined-commit CI |
| Explicit scope overrides defaults | Planning-only requests stay planning-only |
| One claimed issue per session | Track ownership and dependencies; refresh the authorized queue after completion |
| Separate branch and worktree | One independent change per worktree, based on current `origin/main` |
| Meaningful TDD | Confirm a relevant failing test before implementing testable behavior |
| Emulator acceptance | Browser/API acceptance in isolated fixtures and temporary output directories |
| Physical-device validation | Real RTX 3060 checks for GPU inference, memory, CUDA behavior, and model switching |
| Preserve owner data | Preserve uploads, outputs, cached models, running jobs, and unrelated worktrees |
| Validate integration | Review current-main integration and rerun relevant checks on combined code |
| Documentation exception | Accuracy, links, whitespace, and selected CI; no unnecessary GPU run |
| Separate release authorization | No automatic version bump, release tag, published asset, or deployment |
| Evidence boundaries | Distinguish mocks, real browser behavior, real GPU inference, and visual quality |
| Production triage boundaries | Investigation/filing does not authorize fixes or service changes |

Translate platform-specific requirements by risk rather than copying Android commands, phone permissions, APK signing, Firebase settings, or broken links into this project. No agent delegation is required or enabled by this policy.

## 3. Safe source import and initial Git history

Bootstrap is the one-time exception to starting from an existing `origin/main`: there is no project history yet.

1. Inventory the source and current running-job state.
2. Extend `.gitignore` for all model environments, model caches, generated meshes/splats, logs, reports, browser traces, local credentials, and temporary workspaces. Keep `.env.example` trackable.
3. Add `.gitattributes` for source text and shell line endings, plus `.editorconfig` for consistent editing.
4. Build an explicit staging allowlist. Never use an unreviewed bulk import of the directory.
5. Check staged contents for credentials, personal uploads, absolute owner-specific paths that should be portable, generated artifacts, and large binaries.
6. Initialize `main`, create a minimal reviewed baseline commit, and scan that committed history before pushing it to the empty remote.
7. Develop infrastructure in a `chore/repository-bootstrap` branch and separate worktree, opening the first PR against the baseline.
8. Once initial CI is successful, configure the available branch protections and merge through the selected PR workflow.

Do not commit or push `models/`, `outputs/`, `.venv/`, `node_modules/`, or generated `dist/`. Do not rewrite or delete the local copies. Model weights remain downloadable assets outside Git; Git LFS is not needed for them.

The first source baseline cannot have historical CI evidence. Its local checks and that limitation must be recorded explicitly. The infrastructure PR establishes the checks required for subsequent changes.

## 4. Planned scaffolding

```text
AGENTS.md
README.md
CONTRIBUTING.md
THIRD_PARTY_NOTICES.md
.editorconfig
.gitattributes
.gitignore
.env.example
.python-version
.node-version
Makefile
pyproject.toml / uv.lock
package.json / package-lock.json
.github/
  CODEOWNERS
  PULL_REQUEST_TEMPLATE.md
  ISSUE_TEMPLATE/
    feature.yml
    bug.yml
    investigation.yml
    config.yml
  dependabot.yml
  workflows/
    ci.yml
    security.yml
docs/
  README.md
  getting-started.md
  development.md
  architecture.md
  validation.md
  security.md
  releases.md
  repository-bootstrap-plan.md
  game-character-plan.md
scripts/
  bootstrap.sh
  doctor.py
  check.sh
  ci_validation.py
  docs_validation.py
  repository_data_guard.py
  gpu_smoke.py
security/
  reviewed-assets.json
tests/
  existing API and progress tests
  infrastructure regression tests
  browser acceptance tests
```

Keep the current app layout initially. This task should not simultaneously move all source into a new package or install TripoSR/UniRig. Create worker/backend directories when their implementation begins instead of adding empty abstractions now.

All executable scripts and newly introduced CI/security logic receive relevant validation. File names above are proposed responsibilities, not claims that those files already exist.

## 5. Reproducible developer setup

Pin a tested Python version, Node version, and uv version. Use Python 3.11 as the initial compatibility baseline and the working Node 22 line unless execution-time checks reveal a reason to change. Install dependencies from the existing lockfiles, updating them deliberately for new development tools.

Provide these stable entry points:

| Command | Contract |
|---|---|
| `make bootstrap` | Install locked development dependencies and build the UI; no model download by default |
| `make doctor` | Report versions, CUDA/device readiness, model availability, disk space, and actionable gaps |
| `make models` | Explicitly download the pinned Idol assets |
| `make dev` | Start the documented local development workflow |
| `make run` | Build as needed and start the normal local app |
| `make lint` | Run agreed Python, JavaScript, and workflow checks |
| `make test` | Run deterministic CPU/API/progress tests without model downloads |
| `make test-browser` | Run isolated browser acceptance without GPU inference |
| `make test-gpu` | Run deliberate real inference using a reviewed fixture |
| `make check` | Run the same default checks selected by normal code CI |
| `make check-docs` | Validate documentation links and whitespace |
| `make check-security` | Run the data guard and redacted secret scan |

Scripts must work from a fresh clone and any working directory without hardcoded `/home/andrepaim` paths. Bootstrap must be repeatable and must not silently replace a working CUDA environment or download several gigabytes just to run lint.

Define an explicit, locked CPU-test dependency profile. Include CPU PyTorch so the real module-hook tests execute in CI; a green run that silently skips them is insufficient. Keep the CUDA SDK environment separate from this test profile and verify that profile switching cannot unexpectedly uninstall the running model dependencies.

Add small, reviewed Ruff and ESLint configurations. Limit initial cleanup to what is necessary to establish useful checks; record baseline formatting changes separately when they would obscure behavior changes.

## 6. CI and validation routing

Run CI on every PR, pushes to `main`, and manual dispatch. Prefer an always-running aggregate check called **`Required validation`** instead of path-filtering the entire workflow away.

| Job | Evidence |
|---|---|
| Validation selection | Complete Git base/head diff; explicit docs-only allowlist; unknown paths select full checks |
| Python checks | Lint, deterministic tests, and real CPU PyTorch hook tests |
| Frontend checks | Locked npm install, lint, production build |
| Browser acceptance | Upload/control flow, polling, progress/ETA, errors, downloads, and repeated viewer lifecycle |
| Documentation | Changed links/anchors, affected inbound links, and whitespace |
| Repository security | Redacted history scan and generated/private-file guard |
| Required validation | Fail unless every required selected job succeeded |

Adapt the useful DistillPod classifier, link-validator, and guard patterns, with project-specific allowlists and regression tests. Do not copy its full Android/Firebase CI stack.

Classifier tests must cover mixed code/docs changes, code under `docs/`, renames/deletions, executable files, missing/shallow diff evidence, and unexpected skipped jobs. Start with full validation until the docs-only route and gate are proven safe.

Use reviewed commit-SHA pins for Actions, read-only default token permissions, checkout without persisted credentials, timeouts, and cancellation of superseded runs. Do not execute untrusted PR code in a privileged `pull_request_target` context. See [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use).

Keep browser fixtures synthetic or reviewed public assets. A tiny splat fixture may be generated deterministically for viewer lifecycle checks; it proves browser behavior, not reconstruction quality. Software WebGL checks must record renderer limitations. If software rendering cannot establish a required visual property, validate it locally and record the result.

Upload only allowlisted build/test reports and synthetic failure screenshots with short retention. Never upload a workspace, model cache, personal image, generated user asset, or unredacted server log.

## 7. Real GPU validation

GPU inference is a separate evidence gate, not something a hosted CPU job can certify.

For inference, CUDA/toolchain, model-source, GPU scheduling, or significant viewer/inference memory changes, require a run on the actual RTX 3060. Record commit SHA, working-tree state, GPU/driver/runtime, model revisions, settings, time, peak memory where measured, artifact validation, and limitations.

The initial GPU smoke test uses an explicitly reviewed public or synthetic input and temporary output storage. Validate that the PLY parses and contains the expected number of records; do not hardcode universal byte equality across toolchain changes. Retain visual inspection as a separate quality observation.

For future character work, extend acceptance with textured mesh integrity, skeleton/weights, round-trip exports, and Idol → character → Idol switching as described in the feature plan.

Ordinary hosted CI uses no GPU and downloads no model weights. Keep hardware evidence manual initially. A persistent self-hosted Actions runner on the owner's workstation is a later, separately scoped decision; untrusted PR jobs must not run there.

If a required real-GPU check is unavailable or fails, leave that feature unmerged and record the blocker. Low-risk documentation or pure logic changes do not require unrelated inference runs.

## 8. Repository security and dependency maintenance

Adapt DistillPod's guard to reject tracked model checkpoints, generated PLY/GLB/FBX/Blend assets, databases, secrets, owner logs, output directories, archives, and oversized binaries. Reviewed test assets need an exact checksum and provenance entry in `security/reviewed-assets.json`; the guard must not automatically approve them.

Inspect current tracked objects and every new commit in the proposed range, including files committed and later deleted. Validate initial-import behavior and missing manifests. Scan fetched history with a version/checksum-pinned Gitleaks installation and fully redacted output.

Enable GitHub secret scanning/push protection where the repository's account and visibility support them; keep the repository scanner regardless. Availability differs for public and private repositories, so record actual settings rather than assuming they are active. See [GitHub secret scanning](https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning).

Configure weekly dependency updates for GitHub Actions and npm. Select a documented tool configuration for Python/uv lock updates after verifying current support; dependency PRs follow the same validation gates and are not blindly merged.

Document model-source licenses and notices, including the distinct DINOv3 terms. The application license must not imply that all downloaded model weights share it.

## 9. Repository settings and integration policy

Configure squash merging, automatic branch deletion, and PR-based integration. Disable force pushes and deletion for `main` where the account supports enforcement. Require the stable aggregate CI context and current-base validation.

Set `CODEOWNERS` to the selected owner, but do not require an impossible self-approval in a solo-maintainer repository. Record meaningful review and validation without representing the author as an independent reviewer. Revisit approval requirements when another maintainer joins.

Ruleset availability depends on account plan and repository visibility. Check support during setup and explicitly report any enforcement gap; do not claim a ruleset exists because its desired settings are documented. A private personal repository may require a different account plan for server enforcement. See [GitHub rulesets availability](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).

Repository-policy documentation still applies when server enforcement is unavailable. Do not silently purchase an upgrade or change the requested visibility to obtain it.

Before completing each implementation increment: fetch current `origin/main`, integrate intervening changes, review the combined diff, run relevant checks, merge its PR, and verify CI on the resulting `main` commit. Failed combined CI is unfinished work.

## 10. Issues, milestones, and optional project board

Create actionable issues with scope, acceptance criteria, dependencies, validation, and risk. Use labels such as `type:feature`, `type:bug`, `type:infra`, `type:docs`, `priority:P0`–`priority:P3`, `status:ready`, `status:blocked`, and `area:gpu`/`api`/`web`/`models`/`ci`.

An issue is ready only when decisions and dependencies are satisfied. A backlog entry does not authorize its implementation. Claim one issue per session; record a concrete blocker and release ownership when work cannot proceed.

Proposed bootstrap backlog:

| Order | Issue | Acceptance | Dependencies |
|---|---|---|---|
| 1 | Safe source import and repository creation | Reviewed source-only history pushed; local assets preserved | Identity/visibility |
| 2 | Agent policy and contributor docs | Adapted rules installed; links and commands reviewed | 1 |
| 3 | Reproducible setup and doctor | Fresh clone builds; setup reports missing CUDA/models clearly | 1 |
| 4 | CPU checks and browser harness | Tests execute without model downloads; no unintended skips | 3 |
| 5 | Secret/data guards | Positive/negative guard cases pass; import scans clean | 1 |
| 6 | CI, settings, and required gate | Code/docs routes tested; settings verified; combined CI green | 2–5 |
| 7 | GPU protocol and bootstrap acceptance | Exact-revision RTX 3060 evidence; clean-clone instructions verified | 3, 4, 6 |
| 8 | Character pipeline feasibility | Feature milestone A acceptance met | Bootstrap complete; separately authorized implementation |

Use milestones **Repository foundation**, **Character feasibility**, **Character MVP**, and **Animation support**. Split the existing character plan into ready issues as its decisions become concrete.

An optional private GitHub Project board can mirror Backlog, Ready, In Progress, Blocked, In Review, and Done. Check owner/project access first; existing CLI repository scopes do not prove permission to manage Projects. Repository issues and milestones remain the source of truth if project-board setup is unavailable.

## 11. Documentation and evidence

Provide a portable README with prerequisites, locked setup, model download, local launch, testing, output locations, and troubleshooting. Add a docs index that clearly distinguishes implemented behavior from proposed character work.

Document architecture, exclusive GPU execution, environment boundaries, model provenance, local storage, validation commands, and release ownership. Use small sanitized evidence receipts; keep personal artifacts and raw diagnostics outside Git.

The release guide describes how an explicitly requested source/package release will be validated and published. Do not add automatic tag creation, version bumps, GitHub Releases, container pushes, or deployment on merge. Decide distribution formats when a release is requested instead of adding untested Docker or Kubernetes infrastructure now.

## 12. Bootstrap acceptance and execution sequence

1. Finalize repository identity and inspect active jobs and intended import files.
2. Prepare source hygiene, run baseline checks in isolation, initialize Git, and scan the initial commit.
3. Create the remote and push the reviewed baseline.
4. Use a dedicated bootstrap worktree and PR for policy, setup, tests, guards, and workflows. Split reviewable increments as needed.
5. Exercise CI and failure paths, then configure supported repository protections against proven check names.
6. Integrate current `main`, merge the infrastructure changes, and verify CI on the combined commit.
7. Validate a temporary fresh clone: locked install, production frontend build, default checks, no implicit model download, and readiness without a GPU.
8. Run required local GPU acceptance against the exact final revision without disturbing user jobs or data. If a restart is needed, wait for the active job to finish.
9. Record repository URL, effective settings, command results, hardware evidence, remaining entitlement/access gaps, and ready next issues.

Bootstrap is complete when a fresh clone can build and test the current solution, the existing local inference flow still works, policy and CI are active, generated/private files stay out of history, and remaining limitations are explicit.

The Game Character implementation starts after this foundation is complete and its implementation is authorized. Bootstrap execution does not itself start the character feature or its issue-processing loop.
