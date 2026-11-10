# Repository security and model provenance

Keep local inputs, outputs, credentials, model weights, caches, reports, and owner diagnostics outside Git and CI artifacts. `.gitignore` is a convenience; the committed-object guard independently checks tracked files and every new commit, including files later deleted.

`make check-security` runs the guard and a checksum-pinned Gitleaks 8.30.1 history scan with fully redacted output. It installs the scanner under ignored `.local/tools` when absent. `BASE_SHA=<full-sha> make check-security` also checks each new commit. The guard requires `security/reviewed-assets.json` and rejects private/generated file types, renamed SQLite data, output/model folders, and oversized files. Media/archives need exact path/checksum review; never add a checksum only to make CI green. Text still requires human review.

Security CI runs on every PR/main push through the required gate, plus weekly and manual scans. Workflow jobs have read-only permissions. No workflow uploads workspaces, personal logs, model files, or source snapshots. GitHub secret scanning/push protection settings are verified during setup; repository checks remain independent.

Dependency updates are proposed weekly for Actions, npm, and uv. Review model/runtime compatibility and licenses when upgrading. Public inputs for tests need provenance; procedural fixtures avoid committing user media.

Model revisions and public sources are recorded in `model_setup.py` and the [README](../README.md). DINOv3 retains Meta's license and notice even though weights come from a public community mirror. The public FLUX.2 Klein VAE uses its own Apache-2.0 terms. App source availability does not relicense downloaded model components. See [third-party notices](../THIRD_PARTY_NOTICES.md).

Report a sensitive issue privately to the repository owner rather than including credentials or personal artifacts in a public ticket. Do not include raw model inputs/results in reports. Coordinate credential rotation and historical cleanup if an exposure is confirmed.

ESLint currently requests minimatch 10, which npm reports affected by GHSA-g3hv-75wg-m249. The npm override pins minimatch 11.0.1, the patched release, with the supported Node 22 runtime. Lint/build/browser checks validate the tooling combination; remove the override when upstream permits a patched version directly.
