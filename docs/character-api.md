# Private character authoring API

Status: opt-in M2 API and M3 local/manual foundation. The [browser workflow](character-workflow.md) uses these routes; model adapters and quality acceptance follow separately. This increment does not certify the full image-to-playable pipeline or the corpus quality gates.

## Enable locally

On Linux/WSL with pidfd support, start the existing loopback app with `IDOL_CHARACTERS=1 ./run.sh`. The feature is disabled by default. `/api/status` reports `characters.enabled`, `ready` and the two available stages: `input` and `assessment`. No model, provider, paid service or external image transfer is enabled.

The private store defaults to `.local/characters`; `IDOL_CHARACTER_STORE` and `IDOL_CHARACTER_RESOURCE` are server-side overrides for isolated installations/tests. Keep the store outside public/static directories. It is separate from legacy `outputs/`; no migration or cleanup runs. Only one character service can own the namespace. Legacy inference/cache coordination is still a later integration gate, so no CUDA stages are registered here.

Mutations and worker launches run on the persistent event-loop/service thread, satisfying Linux parent-death semantics. The service polls registered subprocesses, validates completion, and reconciles interrupted stages on startup through the [executor](character-executor.md). A wrong-thread mutation fails explicitly. Shutdown stops/reaps owned workers before releasing ownership.

## Routes

| Route | Behavior |
|---|---|
| `POST /api/characters` | Multipart `request_id` (32 lowercase hex characters) and `image`; first accepted identity returns 202, duplicate identity/same image returns 200 and the same character |
| `GET /api/characters` | Private character statuses; corrupt records receive a safe diagnostic |
| `GET /api/characters/{id}` | Durable stage states/attempts, available stages and selected artifact links |
| `POST /api/characters/{id}/input` | Typed image confirmation/crop correction; starts or reuses the input stage |
| `POST /api/characters/{id}/assessment` | Typed manual body-plan/orientation/scale/suitability review |
| `POST /api/characters/{id}/stages/{stage}/retry` | Validated settings for an available stage; verified success is reused |
| `POST /api/characters/{id}/cancel` | Stop/reap the owned worker, then record cancellation |
| `GET /api/characters/{id}/artifacts/{stage}/{name}` | Bounded hash-verified selected artifact; internal receipts/logs/configuration are unavailable |

Generate a fresh random request identity for a new image. Reusing an accepted identity with different bytes returns 409. Concurrent identical submissions share one attempt. Duplicate upload reconnects rather than implicitly retrying a failed stage. Explicit retry creates a new attempt when the existing result is not a verified cache hit. Unsupported/unregistered stages return 422; no request supplies argv, filesystem paths, a validator or a success decision.

New routes require a loopback Host and same-origin mutations (or an origin-free local client). Responses use `Cache-Control: no-store` and `nosniff`. Upload transfer is bounded at 20 MiB plus 64 KiB multipart overhead, with a separate 20 MiB file limit. Content validation checks still PNG/JPEG/WebP, at least 16 pixels per dimension and at most 25 million pixels before expensive work. Animation, malformed images and decompression bombs are rejected. These bounds are parser/resource safeguards, not reconstruction-quality thresholds.

## Input and review semantics

Original bytes are privately published before a worker starts, with a schema-v1 request identity binding ID, hash and safe reference. A confirmed crop uses oriented image coordinates `[x0,y0,x1,y1]`, stays inside the image and is at least 16 pixels per dimension. The worker applies EXIF orientation, converts to RGBA, crops and limits the longest edge to 1024 pixels. It strips metadata from the prepared PNG, retaining the exact original separately. It preserves decoded channel values; it does not perform ICC color conversion or subject segmentation. The user must review the prepared subject/crop.

An initial input result enters `awaiting_review`. Submit `{"confirmed":true}` (and optional crop) to rerun deterministic preparation with recorded approval and validation. This is not a generic promotion of arbitrary output. Context-aware validators receive an isolated copy of the original claimed parameters; a command builder cannot mutate those approval fields. The receipt binds the decision to copied output hashes.

Manual anatomy fields are `body_plan` (`unknown`, `biped`, `quadruped`, `swimmer`, `unsupported`), `species` (`person`, `dog`, `cat`, `fish`, `shark`, `other`), `front_axis` (`+z`, `-z`, `+x`, `-x`), `scale_m` (desired longest extent, positive and at most 100 metres), `single_subject`, `full_body`, `limbs_separable`, and `confirmed`. The scale default is a proposal until confirmed. Choose anatomy rather than species alone for anthropomorphic characters.

A supported body family with all explicit review/suitability confirmations can pass the assessment stage. Unknown/incomplete review pauses; an explicitly unsupported plan is rejected. The report records `source: manual`. It is an annotation, not an AI proposal, proof of unseen anatomy, or proof that a motion profile exists. Skeleton, deformation and playable acceptance remain later gates. No external reasoning calls occur.

Input corrections invalidate dependent stages; anatomy corrections preserve independent splat/mesh stages. Original uploads remain downloadable even when preparation fails or is cancelled. Previous metadata, attempted outputs and orphaned publications stay on disk; only current selected references are exposed by these routes. An accepted-history browsing API is not provided by this increment.

## Failure and privacy

The service exposes stage state and generated artifact names/links, not uploaded filenames, absolute paths, raw worker logs, lease identities or credentials. The original download is an attachment named `original.bin`; preview is a rewritten PNG. Reference validation, anchored no-symlink reads, byte/size checks and bounded reads precede serving artifacts. Corrupt or redirected artifacts return 409. Files are preserved.

A post-publication uncertain commit returns 503 and blocks new mutations until storage is resolved and the service is reopened/reconciled. It does not return false success or blindly overwrite visible completion. Partial publications and older artifacts remain available for local inspection. Missing models and later GPU failures are not represented by the CPU-only readiness flag.

## Validation

API tests use actual registered PIL subprocesses, synthetic images and disposable private stores. They cover upload/review/correction, idempotency/concurrency, privacy, metadata removal, crop/EXIF orientation, cancellation/retry/original preservation, cache hits, anatomy outcomes, malformed/oversized/bomb inputs, corrupt/symlinked artifacts, loopback/origin checks, disabled/unsupported environments and uncertain publication/restart. Legacy API tests also remain required. Actual HTTP and unchanged GPU lifecycle acceptance are recorded with the final tested revision before merge. Browser reconnection/review UI and model-quality evaluation remain subsequent work.

## Acceptance receipt

Clean tracked runtime revision `05b9dd199450112a17962d204878b82b1bfdd7a1`, 2026-11-11 UTC, Linux/WSL, Python 3.11.15, FastAPI 0.162.2. All 177 Python tests (20 API cases), 33 infrastructure tests, Ruff, documentation links and whitespace pass.

An actual Uvicorn server on an OS-assigned loopback port/private disposable store passed five HTTP scenarios: upload/preparation pause, duplicate reconnect without another attempt, review and verified original/preview downloads, manual annotation, and full server restart preserving status/bytes/identity. The input was a generated cyan rectangle; the manual annotation is a protocol test, not anatomical-quality evidence. Private receipt: `.local/api-http-receipt.json` in the API worktree.

At the same clean runtime revision, all five primitive and six combined-executor CUDA lifecycle scenarios passed again on RTX 3060 12,288 MiB, driver 610.88, Torch 2.15.0+cu132/CUDA 13.2. Workers allocated/initialized/synchronized 256 MiB; allocated/reserved both reported that size. Tests establish cooperating-worker exclusion, cancel/reap/retry, cache reuse and crash/recovery/retry only. They do not establish total VRAM ceilings, actual model inference, reconstruction quality or arbitrary descendant cleanup. The known app was verified idle before stopping and restored ready afterward. Owner inputs, completed outputs, caches and other workspaces were preserved.

The final source changes after this receipt are documentation only. PR and combined-main CI remain required; author review is not independent approval. Browser reconnection/review acceptance is reserved for the subsequent UI increment.
