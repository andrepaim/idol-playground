"""Experimental learned rigging boundary and export integrity checks."""
import hashlib
import json
import math
import os
from pathlib import Path
import struct

from mesh_runtime import run_worker, validate_glb

ROOT = Path(__file__).resolve().parent
PHASES = ('rig_prepare', 'skeleton', 'rig_bind', 'skinning', 'rig_export', 'rig_verify')
MESSAGES = dict(zip(PHASES, ('Preparing the mesh for automatic rigging…', 'Predicting the character skeleton…',
                           'Preparing predicted bones for skinning…', 'Predicting skin weights…',
                           'Preserving appearance and exporting the rig…', 'Reimporting and checking character exports…')))


def backend_python():
    return Path(os.environ.get('IDOL_UNIRIG_PYTHON', str(ROOT / '.venv-unirig/bin/python')))


def backend_installed():
    executable = backend_python()
    try:
        digest = hashlib.sha256((ROOT / 'backends/unirig/uv.lock').read_bytes()).hexdigest()
        return executable.is_file() and (executable.parent.parent / '.backend-ready').read_text().strip() == digest
    except OSError:
        return False


def validate_rigged_glb(data):
    result = validate_glb(data)
    length = struct.unpack_from('<I', data, 12)[0]
    doc = json.loads(data[20:20 + length])
    binary = data[28 + length:]
    try:
        nodes, skins = doc['nodes'], doc['skins']
        if not skins:
            raise ValueError('Missing character skin')
        parents = {}
        def index(items, number):
            if not isinstance(number, int) or not 0 <= number < len(items):
                raise ValueError('Invalid rig reference')
            return items[number]
        for parent, node in enumerate(nodes):
            for child in node.get('children', []):
                index(nodes, child)
                if child in parents:
                    raise ValueError('Invalid skeleton hierarchy: multiple parents')
                parents[child] = parent
        for child in parents:
            seen = set()
            while child in parents:
                if child in seen:
                    raise ValueError('Cyclic skeleton hierarchy')
                seen.add(child); child = parents[child]

        def read(number, kind, component):
            item = index(doc['accessors'], number)
            if item['type'] != kind or item['componentType'] not in component or item.get('sparse'):
                raise ValueError('Invalid skin accessor')
            view = index(doc['bufferViews'], item['bufferView'])
            width = {'VEC4': 4, 'MAT4': 16}[kind]
            code = {5121: 'B', 5123: 'H', 5126: 'f'}[item['componentType']]
            packed = struct.calcsize('<' + width * code)
            stride = view.get('byteStride', packed)
            offset = view.get('byteOffset', 0) + item.get('byteOffset', 0)
            count = item['count']
            end = offset + (count - 1) * stride + packed
            if view.get('buffer', 0) != 0 or count <= 0 or offset < 0 or stride < packed or end > len(binary) or end > view.get('byteOffset', 0) + view['byteLength']:
                raise ValueError('Skin accessor exceeds buffer bounds')
            values = [struct.unpack_from('<' + width * code, binary, offset + row * stride) for row in range(count)]
            if item.get('normalized') and code != 'f':
                scale = 255 if code == 'B' else 65535
                values = [tuple(value / scale for value in row) for row in values]
            return values

        bone_count = 0
        for skin in skins:
            joints = skin['joints']
            if not 2 <= len(joints) <= 512 or len(joints) != len(set(joints)):
                raise ValueError('Invalid joint list')
            for joint in joints:index(nodes, joint)
            matrices = read(skin['inverseBindMatrices'], 'MAT4', {5126})
            if len(matrices) != len(joints):raise ValueError('Missing bind matrices')
            for matrix in matrices:
                a,b,c,d,e,f,g,h,i = (matrix[k] for k in (0,4,8,1,5,9,2,6,10))
                determinant = a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)
                if not all(math.isfinite(value) for value in matrix) or abs(determinant) < 1e-12:
                    raise ValueError('Invalid inverse bind matrix')
            bone_count += len(joints)
        skinned = 0
        for node in nodes:
            if 'mesh' not in node or 'skin' not in node:continue
            skin = index(skins, node['skin'])
            mesh = index(doc['meshes'], node['mesh'])
            for primitive in mesh['primitives']:
                attributes = primitive['attributes']
                if any(key.startswith(('JOINTS_', 'WEIGHTS_')) and key not in ('JOINTS_0', 'WEIGHTS_0') for key in attributes):
                    raise ValueError('More than four skin influences')
                js = read(attributes['JOINTS_0'], 'VEC4', {5121, 5123})
                ws = read(attributes['WEIGHTS_0'], 'VEC4', {5126, 5121, 5123})
                count = index(doc['accessors'], attributes['POSITION'])['count']
                if len(js) != count or len(ws) != count:raise ValueError('Skin vertex count mismatch')
                for joints, weights in zip(js, ws):
                    if any(joint >= len(skin['joints']) for joint in joints):raise ValueError('Invalid vertex joint')
                    if not all(math.isfinite(weight) and 0 <= weight <= 1 for weight in weights) or abs(sum(weights) - 1) > .002:
                        raise ValueError('Invalid or unnormalized skin weight')
                skinned += count
        if not skinned:raise ValueError('No skinned geometry')
        return {**result, 'bones': bone_count, 'skinned_vertices': skinned, 'rigged': True,
                'diagnostic_animation': any(animation.get('channels') for animation in doc.get('animations', []))}
    except (KeyError, IndexError, TypeError, struct.error) as error:
        raise ValueError('Missing or invalid character skin') from error


def generate_rig(source, folder, seed, on_event, cancel):
    import shutil
    folder = Path(folder)
    shutil.copy2(source, folder / 'input.glb')
    environment = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                   'WANDB_DISABLED': 'true', 'WANDB_MODE': 'disabled', 'OMP_NUM_THREADS': '4', 'PYTHONUNBUFFERED': '1'}
    for phase in PHASES:
        on_event({'stage': phase, 'message': MESSAGES[phase]})
        phase_folder = folder / phase
        phase_folder.mkdir()
        command = [str(backend_python()), str(ROOT / 'backends/unirig/worker.py'), '--phase', phase,
                   '--models', str(ROOT / 'models'), '--job', str(folder), '--seed', str(seed)]
        run_worker(command, phase_folder, on_event, cancel, timeout=600, env=environment)
    details = validate_rigged_glb((folder / 'rigged.glb').read_bytes())
    report = json.loads((folder / 'rig.json').read_text())
    if not details['diagnostic_animation'] or report.get('deformation_max', 0) <= 1e-5:
        raise ValueError('Rig binding did not pass the diagnostic deformation check')
    return {**details, **report}
