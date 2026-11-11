"""Coordinator transitions with disposable files; no worker/model execution."""
from datetime import datetime
from hashlib import sha256
import json

import pytest

from character_contracts import invalidate, new_character
from character_store import CharacterStore
from character_coordinator import StageCoordinator, Decision, StageBlocked, StageBusy, StaleClaim, StageValidationError

IDENTITY = 'a' * 32
VERSIONS = {'adapter':'test-v1'}


@pytest.fixture
def setup(tmp_path):
    store = CharacterStore(tmp_path / 'store')
    store.save(new_character(IDENTITY), expected_revision=None)
    worker = tmp_path / 'worker'
    worker.mkdir()
    (worker / 'input.png').write_bytes(b'fixture')
    return StageCoordinator(store), store, worker


def start_input(coordinator, **parameters):
    return coordinator.start(IDENTITY, 'input', parameters, VERSIONS, {}, external_inputs={'upload':sha256(b'fixture').hexdigest()})


def accept(paths):
    assert paths['input.png'].read_bytes() == b'fixture'
    return Decision('accept', {'structure':'synthetic fixture, not a real image'})


def completed_input(setup):
    coordinator, store, worker = setup
    claim = start_input(coordinator)
    coordinator.finish(claim, worker, ['input.png'], accept)
    return coordinator, store, worker


def test_claim_complete_receipt_and_verified_cache(setup):
    coordinator, store, worker = setup
    claim = start_input(coordinator)
    assert claim.attempt == 1 and not claim.cached
    assert store.load(IDENTITY)['stages']['input']['state'] == 'running'
    record = coordinator.finish(claim, worker, ['input.png'], accept)
    assert record['stages']['input']['state'] == 'succeeded'
    assert any(item['path'].endswith('/_validation.json') for item in record['stages']['input']['outputs'])
    receipt = next(a for a in record['stages']['input']['outputs'] if a['path'].endswith('/_validation.json'))
    evidence = json.loads((store.root / IDENTITY / receipt['path']).read_text())
    assert evidence['outputs'] == {'input.png': sha256(b'fixture').hexdigest()}
    assert datetime.fromisoformat(evidence['recorded_at']).utcoffset().total_seconds() == 0
    cached = start_input(coordinator)
    assert cached.cached
    assert store.load(IDENTITY)['revision'] == record['revision']


def test_dependency_and_running_conflicts(setup):
    coordinator, _, _ = setup
    with pytest.raises(StageBlocked):
        coordinator.start(IDENTITY, 'splat', {}, VERSIONS, {'input':['input.png']})
    start_input(coordinator)
    with pytest.raises(StageBusy):
        start_input(coordinator)


def test_explicit_dependency_inputs_and_cache_versions(setup):
    coordinator, store, worker = completed_input(setup)
    with pytest.raises(ValueError):
        coordinator.start(IDENTITY, 'assessment', {}, VERSIONS, {})
    with pytest.raises(ValueError):
        coordinator.start(IDENTITY, 'assessment', {}, VERSIONS, {'input':['missing.png']})
    claim = coordinator.start(IDENTITY, 'assessment', {}, VERSIONS, {'input':['input.png']})
    coordinator.finish(claim, worker, ['input.png'], accept)
    changed = coordinator.start(IDENTITY, 'assessment', {}, {'adapter':'test-v2'}, {'input':['input.png']})
    assert not changed.cached and changed.attempt == 2
    assert store.load(IDENTITY)['stages']['input']['state'] == 'succeeded'


@pytest.mark.parametrize('outcome,state', [('review','awaiting_review'),('reject','failed')])
def test_quality_review_and_rejection_never_accept(setup, outcome, state):
    coordinator, store, worker = setup
    claim = start_input(coordinator)
    record = coordinator.finish(claim, worker, ['input.png'], lambda _: Decision(outcome, {'reason':'needs inspection'}))
    assert record['stages']['input']['state'] == state
    assert not record['stages']['input']['validation_passed']
    assert not store.reusable(IDENTITY, record['stages']['input'], claim.fingerprint)


def test_unapproved_validator_cannot_mark_success(setup):
    coordinator, store, worker = setup
    claim = start_input(coordinator)
    with pytest.raises(StageValidationError):
        coordinator.finish(claim, worker, ['input.png'], lambda _: True)
    assert store.load(IDENTITY)['stages']['input']['state'] == 'failed'


def test_snapshot_modified_by_validator_is_not_accepted(setup):
    coordinator, store, worker = setup
    claim = start_input(coordinator)
    def corrupt(paths):
        paths['input.png'].write_bytes(b'changed')
        return Decision('accept', {})
    with pytest.raises(StageValidationError):
        coordinator.finish(claim, worker, ['input.png'], corrupt)
    assert store.load(IDENTITY)['stages']['input']['state'] == 'failed'
    assert (worker / 'input.png').read_bytes() == b'fixture'


def test_stale_completion_cannot_replace_corrected_record(setup):
    coordinator, store, worker = setup
    claim = start_input(coordinator)
    current = store.load(IDENTITY)
    corrected = invalidate(current, 'input')
    store.save(corrected, expected_revision=current['revision'])
    with pytest.raises(StaleClaim):
        coordinator.finish(claim, worker, ['input.png'], accept)
    assert store.load(IDENTITY) == corrected


@pytest.mark.parametrize('state', ['failed','cancelled','interrupted'])
def test_end_and_retry_preserve_attempts(setup, state):
    coordinator, store, _ = setup
    old = start_input(coordinator)
    coordinator.end(old, state, 'test_reason')
    assert store.load(IDENTITY)['stages']['input']['state'] == state
    retried = start_input(coordinator)
    assert retried.attempt == 2
    with pytest.raises(StaleClaim):
        coordinator.end(old, 'failed', 'late_result')
    assert store.load(IDENTITY)['stages']['input']['state'] == 'running'


def test_wrong_upload_hash_and_corrupt_dependencies_block(setup):
    coordinator, store, worker = setup
    claim = coordinator.start(IDENTITY, 'input', {}, VERSIONS, {}, external_inputs={'upload':'b'*64})
    with pytest.raises(StageValidationError):
        coordinator.finish(claim, worker, ['input.png'], accept)
    assert store.load(IDENTITY)['stages']['input']['state'] == 'failed'
    valid = start_input(coordinator)
    record = coordinator.finish(valid, worker, ['input.png'], accept)
    artifact = next(a for a in record['stages']['input']['outputs'] if a['path'].endswith('/input.png'))
    (store.root / IDENTITY / artifact['path']).write_bytes(b'corrupt')
    with pytest.raises(StageBlocked):
        coordinator.start(IDENTITY, 'assessment', {}, VERSIONS, {'input':['input.png']})


def test_invalid_decisions_versions_end_states_are_rejected(setup):
    coordinator, _, _ = setup
    for outcome, details in [('unknown',{}), ('accept',{'score':float('nan')}), ('accept',True)]:
        with pytest.raises(ValueError):
            Decision(outcome, details)
    with pytest.raises(ValueError):
        coordinator.start(IDENTITY, 'input', {}, {}, {}, external_inputs={'upload':'a'*64})
    claim = start_input(coordinator)
    with pytest.raises(ValueError):
        coordinator.end(claim, 'succeeded', 'cannot_bypass_validation')


def test_input_hashes_must_be_an_explicit_mapping(setup):
    coordinator, _, _ = setup
    with pytest.raises(ValueError):
        coordinator.start(IDENTITY, 'input', {}, VERSIONS, {}, external_inputs=['not-a-mapping'])


def test_correction_during_validation_preserves_new_revision(setup):
    coordinator, store, worker = setup
    claim = start_input(coordinator)
    corrected = None
    def edit_during_validation(_):
        nonlocal corrected
        previous = store.load(IDENTITY)
        corrected = invalidate(previous, 'input')
        store.save(corrected, expected_revision=previous['revision'])
        return Decision('accept', {})
    with pytest.raises(StaleClaim):
        coordinator.finish(claim, worker, ['input.png'], edit_during_validation)
    assert store.load(IDENTITY) == corrected


@pytest.mark.parametrize('changed,preserved,invalidated', [
    ('assessment', ['splat','mesh'], ['prepare','skin','motion','package']),
    ('mapping', ['splat','mesh','skin'], ['motion','package']),
])
def test_changes_preserve_independent_expensive_stages(setup, changed, preserved, invalidated):
    from character_contracts import DEPENDENCIES
    coordinator, store, worker = setup
    for stage, dependencies in DEPENDENCIES.items():
        if stage == 'input':
            claim = start_input(coordinator)
        else:
            claim = coordinator.start(IDENTITY, stage, {}, VERSIONS, {dep:['input.png'] for dep in dependencies})
        coordinator.finish(claim, worker, ['input.png'], accept)
    coordinator.start(IDENTITY, changed, {'correction':True}, VERSIONS, {dep:['input.png'] for dep in DEPENDENCIES[changed]})
    record = store.load(IDENTITY)
    assert all(record['stages'][name]['state'] == 'succeeded' for name in preserved)
    assert all(record['stages'][name]['state'] == 'pending' for name in invalidated)


def test_uncertain_metadata_commit_is_not_overwritten_as_failed(setup, monkeypatch):
    import character_store
    coordinator, store, worker = setup
    claim = start_input(coordinator)
    original = character_store._sync_directory
    def fail_after_pointer(path):
        if path == store.root / IDENTITY:
            raise OSError('Injected sync failure')
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(character_store, '_sync_directory', fail_after_pointer)
        with pytest.raises(character_store.CommitUncertain):
            coordinator.finish(claim, worker, ['input.png'], accept)
    # The caller must reconcile/resync; no success was returned and no blind
    # failure write superseded the already-visible, validated revision.
    assert store.load(IDENTITY)['stages']['input']['state'] == 'succeeded'
