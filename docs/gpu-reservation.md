# Application GPU reservation

Status: opt-in M2 ownership increment, in validation. It does not register character model adapters or complete global worker/cache integration.

On Linux/WSL, set IDOL_GPU_RESERVATION=1 for an application reservation held through startup, idle cached Idol tensors, work and shutdown. The default is disabled, preserving the existing startup behavior and Apple Silicon path. All cooperating instances must use the same resource file. The default is the private cuda.lock under the user's XDG cache idol-playground directory, shared across worktrees. IDOL_GPU_RESOURCE can explicitly select an absolute file for configuration or disposable acceptance tests.

A conflicting opted-in app fails startup before character-store recovery or model loading. The message asks the operator to let existing work finish or close its owning app. There is no blind PID kill, force-unlock, file replacement or automatic deletion. The status API adds only enabled/held booleans; paths, descriptors and owner identities remain private.

The file must be empty, regular, owned by the current user, mode 0600 and have one link. Symlinks, changed identities and unsafe existing files are refused without replacing them. New directories/files use private permissions. Do not remove or replace a reservation file while an owner is running.

## Lifetime and inheritance

The application context reserves before starting character recovery. It retains the reservation while services close and legacy executor jobs stop/reap. Cached Idol tensors are explicitly released before reservation close in the opted-in path.

Both the legacy bounded-worker launcher and the cooperating WorkerLease bootstrap pass the reservation descriptor to registered direct children. The descriptor shares the parent's open-file description. Parent close/death therefore leaves a still-running inheriting child holding the reservation. Closing never uses LOCK_UN, which would unlock the shared description for its children.

A surviving legacy worker can cause startup refusal until it finishes; this feature does not invent recovery authority over a foreign process. Existing worker leases retain their verified identity/cancellation/recovery rules. Their per-attempt resource file is separate from the application reservation: configuring both to the same file is rejected before recovery.

This is advisory coordination between opted-in instances using one shared path. It cannot exclude older/nonparticipating applications, other CUDA programs, different overrides or destructive external changes to the file. The reservation is conservative: it reserves an entire application, including idle cache, rather than queuing GPU work between servers.

Only registered direct launchers are covered by descriptor propagation. Arbitrary vendor descendants, SDK thread/process trees and changed multi-GPU strategies remain unvalidated. Future model adapters still need their specific descendant audit, same-app GPU admission/cache handoff and actual hardware checks before becoming available. Current character stages remain input/manual assessment only.

## Validation

Tests first failed on the absent module. Real disposable processes establish owner exclusion, safe private files, shared default paths, inherited descriptor retention after parent close/death, both launch bridges and cancellation/reaping. API lifecycle tests establish startup refusal before recovery, cleanup on setup error, disabled behavior, configuration-collision refusal and shutdown ordering. A subsequent test first failed because cached tensors were not explicitly released before reservation close; the opted-in shutdown path now performs that release while still reserved.

Actual RTX 3060 acceptance is required before merging this lifecycle change: cold/warm cached Idol requests, competing app refusal, CUDA-child retention across parent death, cancellation/reaping and release/retry, with isolated outputs and restored owner app. CPU fixtures alone do not certify CUDA cleanup or inference. Hardware receipt and remaining limitations are pending; no performance, total GPU-memory ceiling, reconstruction-quality or general vendor-tree claim is made.
