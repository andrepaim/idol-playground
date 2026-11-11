# Application GPU reservation

Status: opt-in M2 ownership increment merged in PR #67 with successful combined-main CI. It does not register character model adapters or complete global worker/cache integration.

On Linux/WSL, set IDOL_GPU_RESERVATION=1 for an application reservation held through startup, idle cached Idol tensors, work and shutdown. The default is disabled, preserving the existing startup behavior and Apple Silicon path. All cooperating instances must use the same resource file. The default is the private cuda.lock under the user's XDG cache idol-playground directory, shared across worktrees. IDOL_GPU_RESOURCE can explicitly select an absolute file for configuration or disposable acceptance tests.

A conflicting opted-in app fails startup before character-store recovery or model loading. The message asks the operator to let existing work finish or close its owning app. There is no blind PID kill, force-unlock, file replacement or automatic deletion. The status API adds only enabled/held booleans; paths, descriptors and owner identities remain private.

The file must be empty, regular, owned by the current user, mode 0600 and have one link. Symlinks, changed identities and unsafe existing files are refused without replacing them. New directories/files use private permissions. Do not remove or replace a reservation file while an owner is running.

Use one Uvicorn worker for an opted-in GPU app. Starting multiple GPU-capable worker processes deliberately conflicts with the single application reservation; a development frontend can continue to use the existing owning backend.

## Lifetime and inheritance

The application context reserves before starting character recovery. It retains the reservation while services close and legacy executor jobs stop/reap. Cached Idol tensors are explicitly released before reservation close in the opted-in path.

Both the legacy bounded-worker launcher and the cooperating WorkerLease bootstrap pass the reservation descriptor to registered direct children. The descriptor shares the parent's open-file description. Parent close/death therefore leaves a still-running inheriting child holding the reservation. Closing never uses LOCK_UN, which would unlock the shared description for its children.

A surviving legacy worker can cause startup refusal until it finishes; this feature does not invent recovery authority over a foreign process. Existing worker leases retain their verified identity/cancellation/recovery rules. Their per-attempt resource file is separate from the application reservation: configuring both to the same file is rejected before recovery.

This is advisory coordination between opted-in instances using one shared path. It cannot exclude older/nonparticipating applications, other CUDA programs, different overrides or destructive external changes to the file. The reservation is conservative: it reserves an entire application, including idle cache, rather than queuing GPU work between servers.

Only registered direct launchers are covered by descriptor propagation. Arbitrary vendor descendants, SDK thread/process trees and changed multi-GPU strategies remain unvalidated. Future model adapters still need their specific descendant audit, same-app GPU admission/cache handoff and actual hardware checks before becoming available. Current character stages remain input/manual assessment only.

## Validation

Tests first failed on the absent module. Real disposable processes establish owner exclusion, safe private files, shared default paths, inherited descriptor retention after parent close/death, both launch bridges and cancellation/reaping. API lifecycle tests establish startup refusal before recovery, cleanup on setup error, disabled behavior, configuration-collision refusal and shutdown ordering. A subsequent test first failed because cached tensors were not explicitly released before reservation close; the opted-in shutdown path now performs that release while still reserved.

Actual RTX 3060 acceptance is required before merging this lifecycle change: cold/warm cached Idol requests, competing app refusal, CUDA-child retention across parent death, cancellation/reaping and release/retry, with isolated outputs and restored owner app. CPU fixtures alone do not certify CUDA cleanup or inference. The recorded hardware receipt below has this limited scope; no performance, total GPU-memory ceiling, reconstruction-quality or general vendor-tree claim is made.

## Recorded acceptance

Clean tracked runtime bd82c69026e60141dac3932c1251b79fa71ad4c0, 2026-11-11 UTC: all six selected hardware scenarios passed on NVIDIA RTX 3060, driver 610.88, 12,288 MiB, PyTorch 2.15.0+cu132/CUDA 13.2. The app ran in an isolated worktree with separate outputs/store, existing pinned offline model caches and a disposable shared reservation file. All participating test processes used the same resource.

The previously selected CC0 Shiba development PNG (SHA-256 2d677c6855fb3d6dfd654586eea5b643025f2b0cf091852c3c3bcd810757efdb) supplied two actual Idol requests: synthetic mode, ten steps, 65,536 Gaussians, seed 42, guidance 3 and time rescale 3, compilation disabled. Cold request 36.2 seconds; warm 27.6 seconds, with no model-load stage on the second request and cached-model status retained after each. Both PLYs contain 65,536 records with seventeen finite float properties and share SHA-256 3cb2c9fc7396f20ac85af14a84685134413d92958a7e511b68301e462e09471b. These are observations for one input/settings, not a performance or reconstruction-quality gate.

A second app was refused while the first retained its cache, before the second character-store directory was created. Graceful shutdown released the reservation after the app's cleanup. Actual 256 MiB CUDA allocations then established legacy-child retention across parent death, eventual release, lease-backed cancellation/direct-child reaping and successful CUDA retry/normal exit. Private identities/nonces and complete logs remain local.

The first hardware harness attempt incorrectly required exit code zero after sending SIGTERM to Uvicorn. Installed Uvicorn 0.54.0 re-raises captured signals after graceful cleanup; source and completed-shutdown logs verified this behavior. The original failed receipt is preserved. The corrected harness accepts expected SIGTERM termination only with the graceful-shutdown log and released reservation; the complete hardware matrix was rerun and passed on the same unchanged runtime.

The owner's app was restored with character input/manual assessment enabled, no active job and no loaded Idol model. Root outputs, model files and private character-store file-size/mtime inventories were unchanged. Existing source inputs, completed outputs and weights were not replaced.

At the tested runtime, 195 Python tests (eighteen new ownership cases), 33 infrastructure tests, seven controller tests and 26 browser tests pass, with lint/build/docs/whitespace checks. Existing browser regression uses disposable/synthetic inputs and software rendering; it does not establish GPU performance or an enabled character model pipeline. Author review is not independent review. The increment subsequently merged as `aae5b3925d47a9f5b4ca8a74ca0a861229d7df14`; required PR CI `43099962218` and actual combined-main CI `43101325717` succeeded. Same-app cache/model handoff and vendor descendant audits remain unaccepted.
