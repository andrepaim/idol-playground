# Proposed root AGENTS.md

Status: draft for repository bootstrap. These are proposed instructions, not an active root agent file. Derived from the local DistillPod `AGENTS.md`, with browser/GPU requirements substituted for Android-specific requirements. Replace this preface with the project title when installing the policy at the repository root. Local links below describe the planned root-file locations and become valid when the accompanying development documents are created.

## Default issue-handling loop

- When asked to handle repository issues, work through the authorized queue autonomously: select one eligible issue, complete it, refresh the queue, and repeat until no eligible issues remain. Do not ask for confirmation between issues already within the user's authorized scope. Editing this policy or planning the repository alone does not start an issue-processing run.
- Select the highest-priority ready issue using established priority/readiness signals. Prefer work that unblocks other issues and oldest-ready work when priorities are equal. An eligible issue has clear scope and acceptance criteria, satisfied dependencies, necessary authorization, and no active owner in another session. Do not treat all open issues as approved work or invent product decisions to make them ready.
- Claim the issue and record the plan before implementation. Keep at most one active issue per session and respect other sessions' ownership. Split oversized work into independently verifiable increments; do not close a parent before all acceptance criteria are met.
- Features and bug fixes require planning, a separate branch/worktree, TDD for testable behavior, relevant automated checks, applicable browser/API acceptance, and real-GPU validation when required by risk. Documentation-only changes use the Evidence exception.
- Completion includes review, integration with current `origin/main`, validation of combined code, a merged PR, and successful CI on the combined commit. Local code, passing branch checks, or a pushed branch alone do not complete an issue. Link the PR, tested revision, evidence, and limitations; close only when acceptance and required checks are satisfied.
- For an unmet dependency, unavailable GPU/check, unclear decision, or separate authorization requirement, record the blocker and next action. Leave the issue open, release ownership when appropriate, and continue independent eligible work. Do not repeatedly retry an unchanged blocker, bypass checks, or abandon unfinished work silently.
- Refresh priorities, dependencies, and ownership after each issue. Stop when the user asks, authorized scope is exhausted, or no eligible work remains; report completion and blockers. Queue exhaustion does not mean all open issues are resolved. Do not release, bump release versions, tag, or publish assets without a separate explicit release request.

## Default feature workflow

- Treat a feature implementation request as authorization to carry it through planning, implementation, validation, and merging into `main`, unless the user limits its scope. An explicit planning-only request remains planning-only. Release publication requires a separate explicit request.
- Complete a plan before implementation: behavior, acceptance, affected components, compatibility/data risks, steps, and per-change validation. Scale detail to the change, resolve material ambiguities before dependent work, and update the plan when findings change it.
- Use a short-lived feature branch in its own Git worktree. Split larger features into small, independently verifiable increments.
- Use TDD for testable behavior: write a meaningful test, confirm it fails for the expected reason, implement, then refactor with tests passing. Cover relevant failures/regressions. For visual-only or exploratory work where automation adds little value, record that limitation and concrete acceptance checks; do not add tests that merely mirror implementation.
- Before merging, pass relevant automated checks, applicable browser/API acceptance, and real-GPU checks required by the risk assessment. Record revision, environment, scenarios, results, and limitations. Historical hardware results do not validate a changed inference path. Required failed or unavailable checks leave the feature unmerged.
- Feature authorization includes non-destructive local dependency setup and model validation needed for the task. Preserve cached weights, uploads, outputs, ongoing jobs, and unrelated workspaces. Do not delete owner data, replace working environments silently, interrupt active generation, use paid services, change live accounts, or deploy a backend/schema without applicable authorization.
- After acceptance and review, integrate current `origin/main`, validate the combined code, merge through a PR, and verify combined-commit CI. Do not stop at an unmerged implementation when the authorized workflow can be completed.

## Risk-based validation

- Assess actual affected behavior, platform/hardware dependencies, storage/data preservation, selected checks, and evidence limitations in the plan and PR. Reassess after scope changes or integration. Do not classify an entire queue as low risk.
- Relevant automated checks, review, current-main integration, and applicable browser/API acceptance remain required. Pure logic, low-risk UI organization, and content-free reporting may use suitable automated/browser evidence when the rationale and limitations are recorded. Persistence, process lifecycle, and data handling can increase risk even in small changes.
- Require actual GPU validation for inference changes, CUDA/driver/runtime compatibility, model loading/unloading, memory claims, concurrent execution, and other behavior mocks cannot establish. Use the RTX 3060 or the hardware affected by the change. Record its identity and effective settings.
- Browser tests establish the tested browser and renderer behavior. CPU substitutes and software WebGL do not prove CUDA behavior, reconstruction quality, hardware memory usage, or performance on the owner's GPU.
- Validate storage and compatibility changes in isolated temporary directories before touching real artifacts. Preserve existing completed outputs and model caches. Required destructive tests need disposable fixtures or separate explicit authorization.
- Do not waive failed or unavailable required checks. Record blockers and next steps, leave affected work unmerged, and continue independent eligible work. See `docs/validation.md` and `docs/development.md` once created by bootstrap.

## Parallel development

- Use a separate short-lived branch and worktree for each independent change, starting from current `origin/main`. Never switch branches, alter unrelated edits, or launch conflicting builds/inference in another session's workspace.
- Keep changes small and merge completed work frequently. Use temporary feature flags when incomplete behavior must land disabled.
- Before merging, fetch current `main`, integrate intervening changes, review the combined diff, and rerun relevant checks. Separately passing branches do not establish their combination works.
- Keep `main` releasable. Verify CI on the combined commit. Fix or coordinate a revert of regressions promptly; do not publish a failing revision.
- Commit only intended task files. Prefer PRs; an explicit instruction to commit/push directly to `main` authorizes that route. Never force-push `main` to resolve concurrent changes.
- Coordinate exclusive access to the GPU and application port. This policy does not independently authorize spawning agents or assigning work to others.

## Error triage

- A request to inspect diagnostics and file issues authorizes investigation and actionable tickets within that scope. It does not start implementation or authorize releases, deployments, monitoring/account changes, or recurring schedules.
- If recurring triage is authorized, record explicit environments, UTC windows, affected revisions, query limits, and the last completed window. Separate test traffic from actual usage and observation time from ingestion time.
- Prioritize data loss, privacy/security impact, blocked generation/export, recoverability, recurrence, and measured user impact. Expected cancellation or model download waits are not automatically bugs.
- Correlate evidence through job/stage/process identities and revision links. Nearby timestamps or similar error text alone do not prove a common incident. Keep facts, hypotheses, and missing evidence distinct.
- Report incomplete reads and coverage limits; absence of a terminal event does not establish success. Search existing issues and current fixes before filing duplicates.
- Tickets state user-visible failure, expected behavior, priority rationale, versions/environment, evidence, reproduction if known, suspected cause/confidence, and acceptance criteria. A confirmed failure can be actionable without a root cause.
- Keep personal inputs, generated assets, credentials, raw logs, and private identifiers outside public tickets and CI artifacts. Use sanitized summaries and appropriate private evidence links. After an authorized fix, validate the affected flow at the corrected revision.

## Release ownership and authorization

- Releases, tags, distributed binaries/containers, deployment, and publication require an explicit request. A merge or push does not authorize them. Feature sessions do not independently change release versions or metadata.
- Designate one release owner to coordinate version fields, notes, tags, and assets. Follow the repository release checklist once bootstrap creates `docs/releases.md`.
- An explicit release request authorizes completing its documented checklist and publishing verified assets without repeated permission questions. Report blockers rather than bypassing validation.
- Review all changes since the last published release, including compatibility and limitations. Preserve supported settings, outputs, cached assets, and migration/upgrade behavior.
- Publication does not itself authorize destructive local tests, live-account changes, paid services, backend/schema changes, or installing over a personal environment.

## Evidence

- Distinguish implementation, automated tests, browser acceptance, actual GPU inference, and visual/model-quality review. Record revision, environment, settings, and limitations; earlier hardware evidence does not validate all later revisions.
- Documentation-only changes require accuracy, local-link, and `git diff --check` validation. Full build or GPU inference is unnecessary unless build/runtime behavior also changes. CI still follows repository workflows.
- Keep credentials, personal inputs/results, model checkpoints, caches, and owner state out of commits, logs, and CI artifacts. Reviewed public/synthetic test assets require documented provenance and applicable checksums.
- A green CPU CI result cannot replace required real-GPU evidence. Missing account entitlements or unenforced repository protections must be reported explicitly rather than described as active.
