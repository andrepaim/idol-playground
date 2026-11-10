# Release ownership

A feature merge does not authorize a release. Publish tags, source archives, packages, containers, or deployments only after an explicit release request. No automatic publishing workflow is installed.

One release owner coordinates the version, notes, tag, assets, and publication. Review every change since the previous published release; record compatibility, setup changes, model terms, and known limitations. Select a distribution format and validate it before promising it as supported.

For an authorized release:

1. Integrate current main; require successful CI on the intended combined revision.
2. Run risk-required GPU/browser/compatibility acceptance and fresh-clone setup checks.
3. Review notes, dependency/model notices, migration behavior, and sanitized artifact contents.
4. Update version fields intentionally, regenerate affected locks, and validate the release commit through a PR.
5. Publish only the verified tag/revision and explicitly requested assets; verify the resulting GitHub release.

Preserve model caches, saved results, and user settings. Release publication does not authorize destructive local installation, paid services, live-account changes, or backend deployment.
