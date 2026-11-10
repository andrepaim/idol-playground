# Contributing

Start with [development](docs/development.md) and [AGENTS.md](AGENTS.md). New feature work requires a plan and acceptance criteria, a separate branch/worktree, meaningful tests, and risk-appropriate browser/GPU evidence.

Claim one ready issue at a time. Unresolved dependencies and product decisions belong in the issue; creating a ticket does not automatically authorize implementing it. Keep changes small and preserve owner data.

Run `make bootstrap check`, inspect `git diff --check`, and run `make check-security` after committing. Review current-main integration and required checks before merging. Never commit model weights, inputs, generated assets, credentials, or local environments. Use synthetic fixtures and record visual/hardware limitations accurately.

Releases require a separate explicit request. A PR should state the problem, resulting behavior, validation revision/environment/results, risks, and limitations.
