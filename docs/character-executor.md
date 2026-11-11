# Durable stage execution

`character_executor.StageExecutor` connects the [stage coordinator](character-coordinator.md), private store and [cooperating worker protocol](worker-leases.md). This opt-in Linux/WSL component is not wired to existing HTTP routes or model launchers. It supplies no production inference adapters.

## Ownership and adapters

Exactly one executor holds the nonblocking `.service.lock` for a private character store. A second service fails before claiming work or reconciling records. All cooperating workers for one physical resource must use the same explicit resource-lock path, even across stores. Neither lock excludes unrelated processes or the existing application, whose cached model lifecycle still needs integration.

Adapters are registered by trusted Python code with a stage, explicit versions, unique generated output filenames, argv builder and snapshot validator. Requests cannot provide executable commands or validators. The adapter identity and executor protocol version participate in the stage fingerprint. Credentials, raw logs and personal filenames must not be parameters. Adapter versions must change when material command/model behavior changes.

The command builder receives private context: the claim, new attempt workspace, copied parameters and selected named dependency paths. The paths reference previously accepted immutable artifacts; they are never request-supplied source paths. Adapters must treat these inputs as read-only and satisfy the cooperating-worker marker/descriptor/descendant rules. Launch from a stable service thread: Linux parent-death signaling follows the creating thread's lifetime. API integration must use the event-loop/service thread or another persistent launcher, not an expiring request worker thread.

## Execution and completion

A verified cache hit launches nothing and creates no new attempt. Otherwise the coordinator commits a running claim, then the executor creates `CHARACTER/runs/STAGE/ATTEMPT`, private logs and `lease.json`, and launches the registered worker. Existing attempt directories are preserved and refused. No history or owner data is deleted.

`wait` releases the service mutex while blocking on the child, so another caller can cancel or shut down. Timeout preserves ownership and running state. Successful exit/reaping and resource-release verification precede immutable snapshot publication, explicit validation and metadata CAS. Nonzero exit records failure. Review/rejection remain distinct from success; a valid-looking file alone never completes a stage. Stale completion cannot replace corrections. Dependency input artifacts and previous attempts remain available after downstream cancellation/failure.

`cancel` stops verified workers and reaps its child before committing cancellation. `close` cancels/reaps owned attempts before releasing the namespace lock; failed cleanup keeps the service lock held. Use the context manager or explicit `close`. After close, new operations fail. Concurrent waiters observe the already committed terminal result rather than committing it twice.

A post-rename uncertain metadata commit blocks new work and propagates `CommitUncertain`. Shutdown stops workers and preserves any already-visible terminal result; it does not overwrite visible success with failure. Reopen only after the underlying storage fault is resolved, then inspect/reconcile the accepted current pointer. No success is returned for an uncertain write.

## Startup and restart

Startup examines accepted current pointers, never the highest orphan revision. A persisted running stage with a lease is reconciled through process identity, live-parent refusal and verified resource release, then marked interrupted. A crash between claim CAS and lease publication is also handled: an ungranted bootstrap cannot execute its target, and the resource must be observed idle before marking interruption. This idle observation is not a reservation for future work; launch acquires its own lock.

Corrupt records, missing attempt identity, foreign/reused PID, live parent or a still-held resource prevent successful startup. Evidence stays on disk for reconciliation. Startup does not rerun inference or promote partial worker output. Explicit retry creates a new attempt from verified dependency boundaries; accepted expensive dependencies can be reused. The legacy app's output directory is neither scanned nor migrated.

## Validation boundary

Sixteen tests use actual owned disposable subprocesses and isolated stores: success/cache, conflicting service, timeout/duplicate/cancel/retry, failed/rejected/invalid output, close cleanup, claim-before-launch crash boundary, unknown adapters, server crash, cross-store resource contention, stale completion, live-parent refusal, preserved dependencies, concurrent wait/cancel and uncertain completion. Tests first failed on the absent module; the blocking-wait cancellation regression also failed before its fix.

Actual RTX 3060 lifecycle acceptance of this combined layer is required before merge and recorded separately. No model inference, anatomical quality, arbitrary vendor process tree, legacy cache coordination or browser/API integration is established by these tests. Those remain later M2/M3–M10 gates.

## RTX 3060 combined-layer receipt

Clean tracked runtime revision `a6d2a390158ddb74874d3029f86c17fbd4e0cdec`, 2026-11-11 UTC, Linux/WSL, RTX 3060 12,288 MiB, driver 610.88, PyTorch 2.15.0+cu132/CUDA 13.2. Disposable registered workers allocated, initialized and synchronized 256 MiB. Measured PyTorch allocated/reserved were both 268,435,456 bytes, not total device use.

Six scenarios passed through the combined executor: second service's worker launch excluded; cancellation committed after exit/reap; CUDA retry validated/committed; verified cache hit launched nothing; service crash recovered the worker and marked its stage interrupted; subsequent CUDA retry validated/committed. The known app was verified idle before stopping and restored ready afterward. The ignored private receipt is `.local/executor-gpu-receipt.json` in the executor worktree.

Subsequent changes add a disposable crash-during-lease-publication test and documentation only; that test confirms the ungranted target never executes and a replacement service can retry. No model inference path changed. Full PR and combined-main CI remain required; author review is not independent approval.
