"""Read-only local character packaging. No inference, owner-state mutation or network."""
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import struct
from zipfile import ZipFile, ZIP_DEFLATED

MAX_CHARACTER_BYTES = 100 * 1024 * 1024


def build_package(folder: Path, job: dict, root: Path) -> bytes:
    if not isinstance(job, dict) or not isinstance(job.get('walk', {}), dict):
        raise ValueError('Invalid completed job metadata.')
    details = job.get('walk') or {}
    stride = details.get('stride')
    if (job.get('state') != 'complete' or job.get('output_type') != 'walk'
            or details.get('profile') != 'canine-34-v1' or isinstance(stride, bool)
            or not isinstance(stride, (int, float)) or not math.isfinite(stride) or not 0 < stride <= 100):
        raise ValueError('A completed reviewed canine walk with valid stride is required.')
    source = folder / 'walk-inplace.glb'
    if folder.is_symlink() or source.is_symlink() or not source.is_file():
        raise ValueError('Retained in-place GLB is missing or unsafe.')
    with source.open('rb') as stream:
        data = stream.read(MAX_CHARACTER_BYTES + 1)
    if not 20 <= len(data) <= MAX_CHARACTER_BYTES:
        raise ValueError('Character size is invalid or exceeds the 100 MiB sample limit.')
    magic, version, length, chunk_length, kind = struct.unpack_from('<4sIII4s', data)
    if magic != b'glTF' or version != 2 or length != len(data) or kind != b'JSON' or not 0 < chunk_length <= len(data) - 20:
        raise ValueError('Invalid in-place GLB header.')
    try:
        document = json.loads(data[20:20 + chunk_length])
        clips = document.get('animations', [])
        if not any(clip.get('name') == 'Walk_inplace' for clip in clips):
            raise ValueError('Walk_inplace clip is required.')
        for resource in [*document.get('buffers', []), *document.get('images', [])]:
            if 'uri' in resource and not resource['uri'].startswith('data:'):
                raise ValueError('External GLB resources are not supported in portable samples.')
    except (TypeError, AttributeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid in-place GLB document.') from error
    manifest = {
        'schema_version': 1, 'profile': 'canine-34-v1',
        'geometry': {'file': 'character.glb', 'sha256': sha256(data).hexdigest(), 'assumed_horizontal_extent_metres': 2},
        'motion': {'clip': 'Walk_inplace', 'mode': 'inplace', 'stride': stride},
        'limitations': ['Experimental standing hold and walking; inspect anatomy.', 'Character redistribution rights are not established by this export.'],
    }
    result = BytesIO()
    with ZipFile(result, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('character.glb', data)
        archive.writestr('character.json', json.dumps(manifest, indent=2, allow_nan=False) + '\n')
        for name in ('index.html', 'sample.js', 'README.md', 'package.json', 'package-lock.json'):
            archive.writestr(name, (root / 'web' / 'sample-template' / name).read_bytes())
        for name in ('playable-viewer.js', 'character-controller.js'):
            archive.writestr(name, (root / 'web' / name).read_bytes())
        archive.writestr('.node-version', (root / '.node-version').read_bytes())
    return result.getvalue()
