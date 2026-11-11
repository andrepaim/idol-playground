# Character preparation browser workflow

`/characters.html` uses the opt-in [local character API](character-api.md). The studio offers its entry link when the API capability is enabled. The page uses local assets/API only; it does not transfer images to a provider. Existing studio, known-canine play page and portable sample remain separate and compatible.

## Current experience

Choose one still PNG/JPEG/WebP, prepare it, compare original and prepared image, and confirm the crop. Crop fields use oriented original pixels. Then review body family, character type, approximate longest extent, forward direction and visible-body suitability. A user can retain an uncertain/incomplete review without falsely confirming missing anatomy. Unsupported body plans remain unaccepted. Badges distinguish working, needs review, reviewed, stopped, interrupted and failed states.

Original/prepared downloads and the manual anatomy report use generated verified API links. Saved-character selection and a validated `?character=ID` reconnect to durable state. Status polling never submits a new job. Duplicate upload retry retains its immutable request identity; a new file gets a new one. No image bytes or uploaded filenames are saved in URLs or browser storage.

The page shows that 3D reconstruction, rigging, motion and gameplay are not yet enabled in this workflow. “Reviewed” describes the input/manual annotation stage, not a validated mesh, rig or playable character. The existing 3D studio remains available. Model adapters, the evaluated reasoning path and corpus acceptance remain later work.

## Recovery and asynchronous behavior

Stop/retry actions use the API's ownership protocol; the browser does not infer worker death or promote output itself. Refresh and connection loss preserve character identity and use read-only reconnection. An initial failed upload can reconnect to an already persisted request instead of launching a duplicate.

Review controls wait for saved crop/annotation details before accepting edits. A later status reply cannot replace a newer rendered revision. Replies from an older character view cannot alter the current form or diagnostics. Changes invalidate the relevant consent checkbox; a new image resets review fields. Prepared-image fetch/integrity errors offer retry and retain the original.

Local preview Blob URLs are revoked when replaced or the page is hidden. A restored page recreates the preview/reconnects. Selected files receive a bounded magic-header preflight before local preview; server content validation remains authoritative. Messages use text content and artifact links are restricted to the expected same-origin character namespace. The page does not expose raw worker logs/configuration or filesystem paths.

## Evidence and limitations

Browser tests first failed on the missing page. Real isolated Uvicorn/PIL service tests cover upload/review/anatomy, reload with unchanged attempts, connection loss/reconnect, saved selection/crop, invalid identity/mobile layout, explicit Blob disposal and disabled mode. Stop/retry uses a registered owned waiting-worker fixture for deterministic timing; it establishes UI/API ownership binding, not a model cancellation or PIL performance claim.

Delayed-response regressions first failed before the fixes: crop details could arrive after controls became editable, and a stale status reply could regress a newer review. Tests now check both consent preservation and monotonic displayed state. Tests use generated synthetic images/private disposable stores; screenshots use a first-party quadruped development probe, not an independent held-out/model-quality case.

This is a 2D UI change. No inference, model loading, process protocol or CUDA path changes. Browser acceptance establishes the tested Chromium behavior, not GPU performance or anatomical quality. The API revision's separate RTX 3060 lifecycle evidence remains scoped to that unchanged backend path. Author review and combined-main CI are required before completion.
