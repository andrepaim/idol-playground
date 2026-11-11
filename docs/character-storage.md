# Character contract and storage foundation

Status: M2 building blocks used by the opt-in [local character API](character-api.md). Existing generation endpoints and completed outputs retain their current persistence behavior. This code alone does not enable restart recovery or resume inference. See [implementation progress](playable-progress.md).

## Private contracts

`character_contracts.py` validates schema-v1 private records: identity, revision and the complete stage map. It rejects unknown fields/states/versions, malformed hashes and unsafe paths. Artifacts have generated ASCII relative paths, SHA-256 and byte count. These private stage records are distinct from the small downloadable sample's `character.json` manifest.

Stages are input, assessment, splat, mesh, mesh assessment, preparation, skeleton prediction, semantic mapping, skinning, motion and packaging. Input assessment does not invalidate the splat/mesh; post-mesh assessment and preparation do depend on it. Semantic mapping changes invalidate motion/package, while changing skeleton geometry invalidates mapping and skinning too. Future backends whose skinning depends on semantic mapping must change that dependency contract before integration.

`fingerprint` binds stage identity, contract version, named input hashes, JSON parameters and tool/model versions. The executor must supply every relevant input/setting/version; the helper cannot detect omitted dependencies. Nonfinite parameters and non-JSON values are rejected. `invalidate` copies records, increments the revision, clears downstream successful status/fingerprints and preserves old artifact references. Retained artifacts are not proof they can be reused.

## Storage layout and compare-and-swap

`CharacterStore(root)` creates an explicit private namespace. Its parent must already exist. Use a private directory such as `.local/characters` when integrating; do not point it at a legacy job folder or expose the complete namespace through a public static mount. The caller chooses the root, never an uploaded/request-supplied filesystem path.

Each identity has immutable `revisions/<revision>-<sha256>.json` files and an atomic `current.json` pointer. New files use private temporary-file permissions; new directories use mode 0700. A POSIX file lock serializes metadata writers across processes. Save compares the current revision against the caller's expected revision; stale writers get `RevisionConflict` instead of overwriting newer work.

```python
from character_contracts import new_character
from character_store import CharacterStore

store = CharacterStore('.local/characters')  # .local must already exist
record = new_character('a' * 32)
store.save(record, expected_revision=None)
record = store.load('a' * 32)
record['revision'] += 1
record['stages']['input']['state'] = 'running'
store.save(record, expected_revision=0)
```

Writes flush and fsync the temporary file, replace the target atomically on the same filesystem, and fsync the containing directory. Immutable revisions are published before their pointer. Failure before pointer replacement preserves the previous current record. Abandoned revisions remain available; there is no automatic deletion or repair that could destroy useful data.

If rename succeeds but directory fsync fails, `CommitUncertain` means publication durability is unknown. It is incorrect to promise that every write error leaves the old pointer current. Reload and reconcile the observed revision before retrying; blind retry with the previous revision conflicts if the new pointer is already visible. Do not report success after this error or silently waive durability.

## Worker artifact publication

`publish_artifacts(identifier, stage, attempt, source_dir, names)` copies up to 64 named regular files from a server-selected finished worker directory into a new private attempt directory. Names are generated ASCII filenames, not paths. Unknown identities/stages/attempts, duplicates, symlinks and nonregular sources are rejected. The source directory and names must never come directly from an HTTP request or reasoning-model command.

The helper streams bytes and hashes with bounded buffers, detects source size/mtime changes during copying, fsyncs copied files and their directory, renames the directory within the same filesystem, then fsyncs its parent. Each publication has a unique identity even when an attempt number is retried. Source files, earlier completed attempts, partial `.publishing-*` directories and orphaned final directories are preserved.

Publication returns safe artifact references without changing the character record. Validate the **published immutable snapshot**, not the mutable worker originals, then commit succeeded status/fingerprint/references through `save(..., expected_revision=...)`. A stale metadata revision or failed validation leaves the new files unaccepted. An orphan directory is not a reusable completed stage. Post-rename directory-sync errors raise `CommitUncertain`; reconcile rather than blindly accepting or deleting those files.

This publishes only inside the explicit private local store. It does not distribute assets, expose downloads, execute a worker, or grant redistribution rights.

## Integrity and platform boundary

Metadata is capped at 1 MiB, validated against its content-addressed filename, schema, identity and revision. Reads anchor path components to directory descriptors and reject symlinks and nonregular files. Artifact verification streams SHA-256 with a 1 MiB read buffer, checks byte counts and rejects FIFO/device/directory references. No CUDA/device memory claim is involved.

`reusable` requires succeeded status, validated outputs, matching execution fingerprint and matching on-disk bytes. `save` verifies every succeeded stage's current output bytes before publishing metadata. A record can remain inspectable after an artifact corrupts, but reuse fails. The caller must check reuse again before consuming dependencies.

Externally written worker files are not assumed durable: use the copy/publication helper and validate its snapshot before committing success. Execution ownership, retry state transitions, orphan-worker reconciliation, cancellation, recovery and API integration remain subsequent M2 increments. A metadata lock does not establish GPU ownership or prove CUDA cleanup. Existing model/GPU runtime behavior is unchanged.

Durability primitives are intended for Linux/WSL local filesystems with POSIX locks, directory descriptors and directory fsync; acceptance uses actual isolated local files and competing processes. Network filesystems, Windows storage, power-loss hardware behavior and alternate filesystem durability are not certified. Failure/unavailable required primitives must be reported, not replaced by an unlocked write.

## Evidence

Meaningful tests first failed on the absent module. Eight storage tests exercise create/read, stale writers, real competing processes, byte corruption, pointer/revision corruption, symlinks, injected pre-publication failure, post-rename sync uncertainty and nonregular artifact rejection. The FIFO regression failed by accepting an empty named pipe before the regular-file check was implemented. Every fixture lives in a disposable test directory; no owner artifacts, caches or running app are modified.

All 95 Python tests and Ruff pass locally at this increment. Repository CI still validates the PR and its combined commit. Browser/model/GPU acceptance is required when these primitives are connected to affected runtime behavior, not inferred from these storage tests.

Artifact-publication acceptance adds 13 isolated tests: successful publish/metadata/reuse round-trip, invalid names/identities/stages, source links/FIFO, source mutation, injected file-sync failure, post-rename uncertainty, retry identity and preservation of earlier files. All 108 Python tests pass locally. These tests do not establish CUDA lifecycle or integrated job recovery.

`read_artifact` supports a bounded (at most 25 MiB), structurally validated, anchored and byte-verified read independently of stage approval. Previewing an awaiting-review result does not promote it to reusable/succeeded status. The API chooses smaller per-artifact limits and never serves private configuration/log files.
