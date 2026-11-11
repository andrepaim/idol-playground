"""Artifact publication acceptance uses only disposable worker/store fixtures."""
from hashlib import sha256
import os
import stat

import pytest

from character_contracts import new_character
from character_store import CharacterStore, CommitUncertain

IDENTITY = 'a' * 32


@pytest.fixture
def setup(tmp_path):
    store = CharacterStore(tmp_path / 'store')
    record = new_character(IDENTITY)
    store.save(record, expected_revision=None)
    worker = tmp_path / 'worker'
    worker.mkdir()
    (worker / 'input.png').write_bytes(b'fixture')
    return store, worker, record


def test_published_bytes_are_durable_references_but_do_not_commit_success(setup):
    store, worker, record = setup
    outputs = store.publish_artifacts(IDENTITY, 'input', 1, worker, ['input.png'])
    assert store.load(IDENTITY) == record
    artifact = outputs[0]
    assert artifact['sha256'] == sha256(b'fixture').hexdigest()
    assert artifact['bytes'] == 7
    assert (store.root / IDENTITY / artifact['path']).read_bytes() == b'fixture'
    assert (worker / 'input.png').read_bytes() == b'fixture'
    # Later worker changes must not alter the snapshot being validated/accepted.
    (worker / 'input.png').write_bytes(b'changed')
    assert (store.root / IDENTITY / artifact['path']).read_bytes() == b'fixture'
    record['revision'] = 1
    record['stages']['input'].update(state='succeeded', attempt=1, fingerprint='b'*64, validation_passed=True, outputs=outputs)
    store.save(record, expected_revision=0)
    assert store.reusable(IDENTITY, record['stages']['input'], 'b'*64)
    assert not list(store.root.rglob('.publishing-*'))


@pytest.mark.parametrize('names', [[], ['../outside'], ['/absolute'], ['input.png', 'input.png'], ['a\\b'], ['a%2fb'], [None]])
def test_invalid_names_rejected_before_publication(setup, names):
    store, worker, record = setup
    with pytest.raises(ValueError):
        store.publish_artifacts(IDENTITY, 'input', 1, worker, names)
    assert not (store.root / IDENTITY / 'artifacts').exists()
    assert store.load(IDENTITY) == record


def test_rejects_unknown_character_stage_attempt_and_source_links(setup, tmp_path):
    store, worker, _ = setup
    for identifier, stage, attempt in [('b'*32, 'input', 1), (IDENTITY, 'unknown', 1), (IDENTITY, 'input', True), (IDENTITY, 'input', 0)]:
        with pytest.raises(ValueError):
            store.publish_artifacts(identifier, stage, attempt, worker, ['input.png'])
    alias = tmp_path / 'alias'
    alias.symlink_to(worker, target_is_directory=True)
    with pytest.raises(ValueError):
        store.publish_artifacts(IDENTITY, 'input', 1, alias, ['input.png'])
    (worker / 'alias.png').symlink_to(worker / 'input.png')
    with pytest.raises(ValueError):
        store.publish_artifacts(IDENTITY, 'input', 1, worker, ['alias.png'])
    os.mkfifo(worker / 'pipe')
    with pytest.raises(ValueError):
        store.publish_artifacts(IDENTITY, 'input', 1, worker, ['pipe'])


def test_file_sync_failure_keeps_source_record_and_partial_attempt(setup, monkeypatch):
    store, worker, record = setup
    original = os.fsync
    def fail_file(descriptor):
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError('Injected disk failure')
        return original(descriptor)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', fail_file)
        with pytest.raises(OSError):
            store.publish_artifacts(IDENTITY, 'input', 1, worker, ['input.png'])
    assert store.load(IDENTITY) == record
    assert (worker / 'input.png').read_bytes() == b'fixture'
    assert len(list(store.root.rglob('.publishing-*'))) == 1
    outputs = store.publish_artifacts(IDENTITY, 'input', 2, worker, ['input.png'])
    assert (store.root / IDENTITY / outputs[0]['path']).read_bytes() == b'fixture'
    assert len(list(store.root.rglob('.publishing-*'))) == 1


def test_directory_sync_uncertainty_never_marks_stage_success(setup, monkeypatch):
    import character_store
    store, worker, record = setup
    original = character_store._sync_directory
    phase_root = store.root / IDENTITY / 'artifacts' / 'input'
    def fail_published(path):
        if path == phase_root:
            raise OSError('Injected post-rename failure')
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(character_store, '_sync_directory', fail_published)
        with pytest.raises(CommitUncertain):
            store.publish_artifacts(IDENTITY, 'input', 1, worker, ['input.png'])
    assert store.load(IDENTITY) == record
    previous = set(phase_root.iterdir())
    assert len(previous) == 1
    store.publish_artifacts(IDENTITY, 'input', 1, worker, ['input.png'])
    assert previous < set(phase_root.iterdir())


def test_changed_source_during_copy_is_rejected(setup, monkeypatch):
    store, worker, record = setup
    source = worker / 'input.png'
    inode = source.stat().st_ino
    original = os.read
    changed = False
    def mutate(descriptor, size):
        nonlocal changed
        data = original(descriptor, size)
        if os.fstat(descriptor).st_ino == inode and not changed:
            changed = True
            source.write_bytes(b'changed')
            os.utime(source, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns + 1_000_000_000))
        return data
    monkeypatch.setattr(os, 'read', mutate)
    with pytest.raises(ValueError, match='changed'):
        store.publish_artifacts(IDENTITY, 'input', 1, worker, ['input.png'])
    assert store.load(IDENTITY) == record


def test_repeated_attempt_numbers_never_overwrite_published_files(setup):
    store, worker, _ = setup
    first = store.publish_artifacts(IDENTITY, 'input', 1, worker, ['input.png'])
    second = store.publish_artifacts(IDENTITY, 'input', 1, worker, ['input.png'])
    assert first[0]['path'] != second[0]['path']
    assert (store.root / IDENTITY / first[0]['path']).read_bytes() == b'fixture'
