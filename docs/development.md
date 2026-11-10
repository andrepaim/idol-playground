# Development

Follow [AGENTS.md](../AGENTS.md): plan, claim eligible work, use a feature branch and worktree, apply meaningful TDD, validate by risk, integrate current main, merge a PR, and verify combined-commit CI. A release requires a separate explicit request.

```sh
git fetch origin
git worktree add ../idol-my-change -b feature/my-change origin/main
cd ../idol-my-change
make bootstrap
make check
```

Keep one active issue per session and coordinate GPU/port ownership. Worktrees do not share ignored models or environments automatically. Download assets deliberately or link an existing trusted local model directory; never commit it. Do not run concurrent inference or interrupt another session's jobs.

## Environments and commands

`pyproject.toml` declares mutually exclusive `cpu` and `local` extras. `make bootstrap` uses `UV_PROJECT_ENVIRONMENT=.venv-check uv sync --locked --extra cpu --extra dev`; `make setup-local` uses `.venv` and the `local` extra. Never point the CPU profile at a working CUDA environment. `uv run --no-sync` avoids incidental synchronization for ad hoc commands in an installed environment.

| Command | Purpose |
|---|---|
| `make bootstrap` | Locked CPU development install, Chromium, frontend build |
| `make setup-mesh mesh-models` | Separate TripoSR environment and public mesh assets |
| `make test-mesh-backend` | Native surface/UV-normal regressions in the mesh environment |
| `make setup-local` | Locked CUDA SDK environment |
| `make models` | Pinned public model download |
| `make doctor` | Read-only readiness report |
| `make lint` | Ruff and ESLint |
| `make test` | API/progress tests plus infrastructure regressions |
| `make test-browser` | Real Chromium, built UI, synthetic API and splats |
| `make check` | Lint, tests, browser acceptance, docs and whitespace |
| `make check-security` | Committed-history data guard and Gitleaks |
| `make test-gpu` | Deliberate inference; see hardware protocol before running |
| `make run` | Build and serve local generation app |
| `make dev` | Frontend hot reload; backend runs separately below |

For hot reload, run `.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000` and `make dev` in separate terminals. The Vite proxy expects backend port 8000. Use `.venv-check/bin/uvicorn` instead for UI development without inference; readiness then correctly reports missing SDK setup.

CPU tests include real PyTorch module hooks, without downloads or CUDA. Browser tests start and stop their own ephemeral static server. No test targets the owner's running app or stored outputs.

## CI and integration

Every PR and main push starts CI. A complete Git diff selects the narrow docs-only route for non-executable root documentation and `docs/*.md`; unknown paths, mixed changes, symlinks, executable changes, or missing evidence cannot receive this exemption. Push/manual runs use full validation. Security always runs. `Required validation` fails on required failures, cancellations, unexpected omissions, wrong checkout identities, or invalid routing evidence.

Actions are SHA-pinned with read-only default permissions and no persisted checkout credentials. Dependabot proposes weekly Actions/npm/uv changes. Review and hardware validation still apply to dependency upgrades affecting inference.

Before merging, fetch and integrate current main, review the combined diff, rerun relevant checks, then verify CI on the resulting main commit. No independent reviewer is configured for this solo-maintainer project; author review is not independent approval. See [validation](validation.md) for hardware requirements.
