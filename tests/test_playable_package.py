"""Disposable export fixtures; never reads owner uploads or outputs."""
from io import BytesIO
import json
from pathlib import Path
import struct
from zipfile import ZipFile

import pytest

from playable_package import build_package


def fixture(folder):
    document = {'asset': {'version': '2.0'}, 'animations': [{'name': 'Walk_inplace'}]}
    encoded = json.dumps(document).encode()
    encoded += b' ' * (-len(encoded) % 4)
    data = struct.pack('<4sII', b'glTF', 2, 20 + len(encoded)) + struct.pack('<I4s', len(encoded), b'JSON') + encoded
    folder.mkdir()
    (folder / 'walk-inplace.glb').write_bytes(data)
    (folder / 'input.png').write_bytes(b'private source')
    return {'state': 'complete', 'output_type': 'walk', 'walk': {'profile': 'canine-34-v1', 'stride': .18}, 'source_job': 'private-identifier'}


def test_exports_portable_safe_contents_and_retains_source(tmp_path):
    folder = tmp_path / 'source'
    job = fixture(folder)
    with ZipFile(BytesIO(build_package(folder, job, Path(__file__).parents[1]))) as archive:
        names = set(archive.namelist())
        assert {'index.html', 'sample.js', 'character.glb', 'character.json', 'package.json', 'package-lock.json', 'README.md', 'playable-viewer.js', 'character-controller.js'} <= names
        assert not any(name.startswith('/') or '..' in name.split('/') for name in names)
        metadata = json.loads(archive.read('character.json'))
        assert metadata['schema_version'] == 1
        assert metadata['motion']['mode'] == 'inplace'
        assert archive.read('character.glb') == (folder / 'walk-inplace.glb').read_bytes()
        for name in names - {'character.glb'}:
            data = archive.read(name)
            assert b'private-identifier' not in data
            assert b'private source' not in data
            assert str(folder).encode() not in data
    assert (folder / 'input.png').read_bytes() == b'private source'


@pytest.mark.parametrize('changes', [{'state': 'running'}, {'output_type': 'rig'}, {'walk': {'profile': 'other', 'stride': .18}}, {'walk': {'profile': 'canine-34-v1', 'stride': float('nan')}}])
def test_rejects_ineligible_jobs(tmp_path, changes):
    folder = tmp_path / 'source'
    job = fixture(folder)
    job.update(changes)
    with pytest.raises(ValueError):
        build_package(folder, job, Path(__file__).parents[1])


def test_rejects_symlink_and_non_inplace_clip(tmp_path):
    folder = tmp_path / 'source'
    job = fixture(folder)
    original = folder / 'walk-inplace.glb'
    data = original.read_bytes()
    original.write_bytes(data.replace(b'Walk_inplace', b'Walk_forward'))
    with pytest.raises(ValueError):
        build_package(folder, job, Path(__file__).parents[1])
    original.unlink()
    elsewhere = tmp_path / 'outside.glb'
    elsewhere.write_bytes(data)
    original.symlink_to(elsewhere)
    with pytest.raises(ValueError):
        build_package(folder, job, Path(__file__).parents[1])


def test_rejects_missing_oversized_and_corrupt_files(tmp_path, monkeypatch):
    import playable_package
    folder = tmp_path / 'source'
    job = fixture(folder)
    source = folder / 'walk-inplace.glb'
    data = source.read_bytes()
    monkeypatch.setattr(playable_package, 'MAX_CHARACTER_BYTES', 21)
    with pytest.raises(ValueError, match='size'):
        build_package(folder, job, Path(__file__).parents[1])
    monkeypatch.setattr(playable_package, 'MAX_CHARACTER_BYTES', 10000)
    source.write_bytes(b'not a GLB')
    with pytest.raises(ValueError):
        build_package(folder, job, Path(__file__).parents[1])
    source.unlink()
    with pytest.raises(ValueError, match='missing'):
        build_package(folder, job, Path(__file__).parents[1])
    source.write_bytes(data)
    with pytest.raises(ValueError, match='metadata'):
        build_package(folder, [], Path(__file__).parents[1])
