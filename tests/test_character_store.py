"""Actual isolated filesystem/process acceptance, never owner outputs."""
from copy import deepcopy
from hashlib import sha256
import multiprocessing
from pathlib import Path

import pytest

from character_contracts import new_character
from character_store import CharacterStore, RevisionConflict

IDENTITY = 'a' * 32


def test_create_roundtrip_and_optimistic_revision_conflicts(tmp_path):
    store = CharacterStore(tmp_path)
    initial = new_character(IDENTITY)
    assert store.load(IDENTITY) is None
    store.save(initial, expected_revision=None)
    assert store.load(IDENTITY) == initial
    with pytest.raises(RevisionConflict):
        store.save(initial, expected_revision=None)
    changed = deepcopy(initial)
    changed['revision'] = 1
    changed['stages']['input']['state'] = 'running'
    store.save(changed, expected_revision=0)
    with pytest.raises(RevisionConflict):
        store.save(changed, expected_revision=0)
    assert store.load(IDENTITY) == changed
    assert len(list((tmp_path / IDENTITY / 'revisions').glob('*.json'))) == 2


def completed(store, root):
    record = new_character(IDENTITY)
    folder = root / IDENTITY
    folder.mkdir(exist_ok=True)
    (folder / 'input.png').write_bytes(b'fixture')
    record['stages']['input'].update(state='succeeded', fingerprint='b' * 64, validation_passed=True,
        outputs=[{'path': 'input.png', 'sha256': sha256(b'fixture').hexdigest(), 'bytes': 7}])
    return record


def test_checks_bytes_before_success_and_reuse(tmp_path):
    store = CharacterStore(tmp_path)
    record = completed(store, tmp_path)
    assert store.reusable(IDENTITY, record['stages']['input'], 'b' * 64)
    assert not store.reusable(IDENTITY, record['stages']['input'], 'c' * 64)
    store.save(record, expected_revision=None)
    (tmp_path / IDENTITY / 'input.png').write_bytes(b'changed')
    assert not store.reusable(IDENTITY, record['stages']['input'], 'b' * 64)
    assert store.load(IDENTITY) == record  # metadata remains inspectable
    newer = deepcopy(record)
    newer['revision'] = 1
    with pytest.raises(ValueError):
        store.save(newer, expected_revision=0)
    assert store.load(IDENTITY)['revision'] == 0


def test_publish_failure_preserves_previous_revision_and_retry(tmp_path, monkeypatch):
    import os
    store = CharacterStore(tmp_path)
    record = new_character(IDENTITY)
    store.save(record, expected_revision=None)
    revised = deepcopy(record)
    revised['revision'] = 1
    original = os.replace
    def fail_pointer(source, target):
        if Path(target).name == 'current.json':
            raise OSError('Injected disk full')
        return original(source, target)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail_pointer)
        with pytest.raises(OSError):
            store.save(revised, expected_revision=0)
    assert store.load(IDENTITY) == record
    assert not list(tmp_path.rglob('*.tmp'))
    revised['stages']['input']['state'] = 'blocked'
    store.save(revised, expected_revision=0)
    assert store.load(IDENTITY) == revised
    assert len(list((tmp_path / IDENTITY / 'revisions').glob('*.json'))) == 3


def test_corrupt_pointer_revision_and_symlink_are_not_trusted(tmp_path):
    store = CharacterStore(tmp_path)
    record = new_character(IDENTITY)
    store.save(record, expected_revision=None)
    revision = next((tmp_path / IDENTITY / 'revisions').glob('*.json'))
    data = revision.read_bytes()
    revision.write_bytes(data + b'corruption')
    with pytest.raises(ValueError):
        store.load(IDENTITY)
    revision.write_bytes(data)
    pointer = tmp_path / IDENTITY / 'current.json'
    pointer.write_text('{broken')
    with pytest.raises(ValueError):
        store.load(IDENTITY)
    pointer.unlink()
    pointer.symlink_to(revision)
    with pytest.raises(ValueError):
        store.load(IDENTITY)


def test_rejects_artifact_symlinks_and_symlinked_parent(tmp_path):
    root = tmp_path / 'store'
    store = CharacterStore(root)
    record = completed(store, root)
    artifact = root / IDENTITY / 'input.png'
    artifact.unlink()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'input.png').write_bytes(b'fixture')
    artifact.symlink_to(outside / 'input.png')
    assert not store.reusable(IDENTITY, record['stages']['input'], 'b' * 64)
    (root / IDENTITY / 'attempt').symlink_to(outside, target_is_directory=True)
    record['stages']['input']['outputs'][0]['path'] = 'attempt/input.png'
    assert not store.reusable(IDENTITY, record['stages']['input'], 'b' * 64)


def writer(root, start, results):
    store = CharacterStore(Path(root))
    record = store.load(IDENTITY)
    record['revision'] = 1
    start.wait(5)
    try:
        store.save(record, expected_revision=0)
        results.put('saved')
    except RevisionConflict:
        results.put('conflict')


def test_actual_process_writers_cannot_overwrite_each_other(tmp_path):
    store = CharacterStore(tmp_path)
    store.save(new_character(IDENTITY), expected_revision=None)
    context = multiprocessing.get_context('spawn')
    start, results = context.Event(), context.Queue()
    processes = [context.Process(target=writer, args=(str(tmp_path), start, results)) for _ in range(2)]
    for process in processes:
        process.start()
    start.set()
    try:
        assert sorted(results.get(timeout=10) for _ in processes) == ['conflict', 'saved']
    finally:
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join()
    assert store.load(IDENTITY)['revision'] == 1


def test_directory_sync_failure_reports_uncertain_commit(tmp_path, monkeypatch):
    import character_store
    store = CharacterStore(tmp_path)
    record = new_character(IDENTITY)
    store.save(record, expected_revision=None)
    record['revision'] = 1
    original = character_store._sync_directory
    def fail_after_pointer(path):
        if path == tmp_path / IDENTITY:
            raise OSError('Injected directory sync failure')
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(character_store, '_sync_directory', fail_after_pointer)
        with pytest.raises(character_store.CommitUncertain):
            store.save(record, expected_revision=0)
    # Rename already happened. Retrying revision zero blindly must conflict.
    assert store.load(IDENTITY) == record
    with pytest.raises(RevisionConflict):
        store.save(record, expected_revision=0)


def test_special_files_cannot_be_accepted_as_artifacts(tmp_path, monkeypatch):
    import os
    import threading
    store = CharacterStore(tmp_path)
    record = completed(store, tmp_path)
    artifact = tmp_path / IDENTITY / 'input.png'
    artifact.unlink()
    os.mkfifo(artifact)
    keepalive = os.open(artifact, os.O_RDWR | os.O_NONBLOCK)
    opened = threading.Event()
    original = os.open
    def observe(path, *args, **kwargs):
        descriptor = original(path, *args, **kwargs)
        if path == 'input.png':
            opened.set()
        return descriptor
    monkeypatch.setattr(os, 'open', observe)
    stage = record['stages']['input']
    stage['outputs'][0].update(bytes=0, sha256=sha256(b'').hexdigest())
    result = []
    thread = threading.Thread(target=lambda: result.append(store.reusable(IDENTITY, stage, 'b' * 64)), daemon=True)
    thread.start()
    try:
        assert opened.wait(5)
    finally:
        os.close(keepalive)
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert result == [False]


def test_bounded_verified_artifact_read_does_not_approve_stage(tmp_path):
    store=CharacterStore(tmp_path)
    record=completed(store,tmp_path)
    artifact=record['stages']['input']['outputs'][0]
    pending=new_character(IDENTITY);store.save(pending,expected_revision=None)
    assert store.read_artifact(IDENTITY,artifact,limit=7)==b'fixture'
    assert store.load(IDENTITY)==pending
    with pytest.raises(ValueError): store.read_artifact(IDENTITY,artifact,limit=6)
    (tmp_path/IDENTITY/'input.png').write_bytes(b'changed')
    with pytest.raises(ValueError): store.read_artifact(IDENTITY,artifact,limit=7)
    with pytest.raises(ValueError): store.read_artifact(IDENTITY,{**artifact,'path':'../escape'},limit=7)
