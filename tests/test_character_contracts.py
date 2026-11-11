"""Pure stage contracts; no workers, filesystem mutation or owner artifacts."""
from copy import deepcopy
import pytest

from character_contracts import new_character, validate_character, fingerprint, affected_stages, invalidate


def test_new_record_and_unknown_schema_rejection():
    record = new_character('a' * 32)
    assert validate_character(record) == record
    for changes in [{'schema_version': 2}, {'id': '../outside'}, {'revision': True}, {'secret': 'unexpected'}]:
        with pytest.raises(ValueError):
            validate_character({**record, **changes})


def test_success_requires_validated_hashed_outputs():
    record = new_character('a' * 32)
    stage = record['stages']['input']
    stage.update(state='succeeded', fingerprint='b' * 64)
    with pytest.raises(ValueError):
        validate_character(record)
    stage.update(validation_passed=True, outputs=[{'path': 'attempt-1/source.png', 'sha256': 'c' * 64, 'bytes': 100}])
    assert validate_character(record) == record
    stage['outputs'][0]['sha256'] = 'invalid'
    with pytest.raises(ValueError):
        validate_character(record)


@pytest.mark.parametrize('path', ['../secret', '/absolute', 'C:\\secret', 'https://host/file', 'a/../../secret', '.', 'a//b', 'a\\b', 'a/./b', 'a%2fb.glb', 'a?query.glb', 'line\nbreak.glb', ''])
def test_unsafe_artifact_paths_rejected(path):
    record = new_character('a' * 32)
    record['stages']['input']['outputs'] = [{'path': path, 'sha256': 'b' * 64, 'bytes': 10}]
    with pytest.raises(ValueError):
        validate_character(record)


def test_fingerprint_is_canonical_and_binds_every_execution_input():
    a = fingerprint('splat', {'image': 'a' * 64}, {'steps': 10, 'seed': 42}, {'model': 'pinned'})
    assert a == fingerprint('splat', {'image': 'a' * 64}, {'seed': 42, 'steps': 10}, {'model': 'pinned'})
    assert a != fingerprint('splat', {'image': 'b' * 64}, {'steps': 10, 'seed': 42}, {'model': 'pinned'})
    assert a != fingerprint('splat', {'image': 'a' * 64}, {'steps': 11, 'seed': 42}, {'model': 'pinned'})
    assert a != fingerprint('splat', {'image': 'a' * 64}, {'steps': 10, 'seed': 42}, {'model': 'new'})
    for parameters in [{'value': float('nan')}, {'value': float('inf')}, {1: 'ambiguous'}, {'value': object()}]:
        with pytest.raises(ValueError):
            fingerprint('splat', {'image': 'a' * 64}, parameters, {'model': 'pinned'})
    with pytest.raises(ValueError):
        fingerprint('unknown', {}, {}, {})


def test_mapping_changes_preserve_skin_and_reconstruction_but_invalidate_motion():
    assert affected_stages('mapping') == {'mapping', 'motion', 'package'}
    assert {'mapping', 'skin', 'motion', 'package'} <= affected_stages('skeleton')
    assert 'splat' not in affected_stages('assessment')
    assert 'mesh' not in affected_stages('assessment')
    assert set(new_character('a' * 32)['stages']) == affected_stages('input')


def test_invalidation_copies_records_and_retains_artifact_references():
    record = new_character('a' * 32)
    for stage in record['stages'].values():
        stage.update(state='succeeded', validation_passed=True, fingerprint='b' * 64,
                     outputs=[{'path': 'valid.glb', 'sha256': 'c' * 64, 'bytes': 10}])
    before = deepcopy(record)
    revised = invalidate(record, 'mapping')
    assert record == before
    assert revised['revision'] == 1
    assert revised['stages']['motion']['state'] == 'pending'
    assert not revised['stages']['motion']['validation_passed']
    assert revised['stages']['motion']['fingerprint'] is None
    assert revised['stages']['motion']['outputs'] == record['stages']['motion']['outputs']
    assert revised['stages']['skin'] == record['stages']['skin']
    assert validate_character(revised) == revised
