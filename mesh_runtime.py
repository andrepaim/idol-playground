"""Lightweight worker boundary and strict validation for self-contained mesh exports."""
import io
import json
import math
from pathlib import Path
import struct

from PIL import Image


def validate_glb(data):
    if len(data) < 24 or len(data) > 128 * 1024 * 1024:
        raise ValueError('Invalid GLB length')
    magic, version, size = struct.unpack_from('<4sII', data)
    if magic != b'glTF' or version != 2 or size != len(data):
        raise ValueError('Invalid GLB header')
    chunks = {}
    offset = 12
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('Truncated GLB chunk')
        length, kind = struct.unpack_from('<I4s', data, offset)
        offset += 8
        if length % 4 or offset + length > len(data) or kind in chunks:
            raise ValueError('Invalid GLB chunk')
        chunks[kind] = data[offset:offset + length]
        offset += length
    try:
        document = json.loads(chunks[b'JSON'])
        binary = chunks[b'BIN\0']
        buffers = document['buffers']
        if document['asset']['version'] != '2.0' or len(buffers) != 1 or buffers[0].get('uri'):
            raise ValueError('GLB buffers must be embedded')
        if not 0 <= len(binary) - buffers[0]['byteLength'] <= 3:
            raise ValueError('Invalid embedded buffer length')
        views = document['bufferViews']
        accessors = document['accessors']

        def view(index):
            if not isinstance(index,int) or not 0 <= index < len(views):raise ValueError('Invalid buffer view reference')
            item = views[index]
            begin, count = item.get('byteOffset', 0), item['byteLength']
            if item.get('buffer', 0) != 0 or begin < 0 or count <= 0 or begin + count > buffers[0]['byteLength']:
                raise ValueError('Invalid buffer view bounds')
            return binary[begin:begin + count], item

        def accessor(index, types, component_types):
            if not isinstance(index,int) or not 0 <= index < len(accessors):raise ValueError('Invalid accessor reference')
            item = accessors[index]
            if item.get('sparse') or item['type'] not in types or item['componentType'] not in component_types:
                raise ValueError('Unsupported mesh accessor')
            count = item['count']
            if not isinstance(count, int) or count <= 0:
                raise ValueError('Empty mesh accessor')
            raw, definition = view(item['bufferView'])
            width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[item['type']]
            code = {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}[item['componentType']]
            packed = struct.calcsize('<' + code * width)
            stride = definition.get('byteStride', packed)
            begin = item.get('byteOffset', 0)
            if stride < packed or begin < 0 or begin + (count - 1) * stride + packed > len(raw):
                raise ValueError('Mesh accessor exceeds buffer bounds')
            values = [struct.unpack_from('<' + code * width, raw, begin + i * stride) for i in range(count)]
            if item.get('normalized') and code != 'f':
                scale = 255 if code == 'B' else 65535 if code == 'H' else 2**32-1
                values = [tuple(value/scale for value in row) for row in values]
            return values

        images = document.get('images',[])
        textures = document.get('textures',[])
        materials = document.get('materials',[])
        for image in images:
            if image.get('uri') or 'bufferView' not in image:
                raise ValueError('Textures must be embedded')
            raw, _ = view(image['bufferView'])
            if image.get('mimeType') not in {'image/png', 'image/jpeg'}:
                raise ValueError('Unsupported embedded image')
            with Image.open(io.BytesIO(raw)) as decoded:
                if decoded.width > 4096 or decoded.height > 4096:
                    raise ValueError('Texture exceeds supported size')
                decoded.verify()
        vertices, triangles, colored = 0, 0, 0
        for mesh in document['meshes']:
            for primitive in mesh['primitives']:
                if primitive.get('mode', 4) != 4:
                    raise ValueError('Mesh must contain triangles')
                positions = accessor(primitive['attributes']['POSITION'], {'VEC3'}, {5126})
                uvs = accessor(primitive['attributes']['TEXCOORD_0'], {'VEC2'}, {5126}) if 'TEXCOORD_0' in primitive['attributes'] else []
                indices = accessor(primitive['indices'], {'SCALAR'}, {5121, 5123, 5125})
                if (uvs and len(uvs) != len(positions)) or len(indices) % 3:
                    raise ValueError('Invalid mesh UV/index counts')
                if not all(math.isfinite(value) for row in positions + uvs for value in row):
                    raise ValueError('Non-finite mesh geometry')
                if any(index[0] >= len(positions) for index in indices):
                    raise ValueError('Mesh index exceeds vertex count')
                attributes = primitive['attributes']
                if 'COLOR_0' in attributes:
                    definition = accessors[attributes['COLOR_0']]
                    if definition['componentType'] != 5126 and not definition.get('normalized'):
                        raise ValueError('Integer vertex colors must be normalized')
                    colors = accessor(attributes['COLOR_0'], {'VEC3','VEC4'}, {5126,5121,5123})
                    if len(colors) != len(positions) or not all(math.isfinite(value) and 0 <= value <= 1 for row in colors for value in row):
                        raise ValueError('Invalid vertex color data')
                    colored += len(positions)
                else:
                    if not uvs:raise ValueError('Mesh requires vertex colors or UV texture appearance')
                    material = primitive['material']
                    if not isinstance(material,int) or not 0 <= material < len(materials):raise ValueError('Invalid material')
                    texture = materials[material]['pbrMetallicRoughness']['baseColorTexture']['index']
                    if not isinstance(texture,int) or not 0 <= texture < len(textures):raise ValueError('Missing material texture')
                    source = textures[texture]['source']
                    if not 0 <= source < len(images):raise ValueError('Missing material texture')
                vertices += len(positions)
                triangles += len(indices) // 3
        if not vertices or not triangles or not (images or colored):
            raise ValueError('Empty textured mesh')
        return {'vertices': vertices, 'triangles': triangles, 'textures': len(images),
                'appearance': 'vertex_colors' if colored == vertices else 'texture'}
    except (KeyError, IndexError, TypeError, struct.error, json.JSONDecodeError, OSError) as error:
        raise ValueError('Invalid embedded textured mesh') from error


class MeshCancelled(RuntimeError):
    pass


def backend_python():
    import os
    return Path(os.environ.get('IDOL_TRIPOSR_PYTHON', str(Path(__file__).resolve().parent / '.venv-triposr/bin/python')))


def backend_installed():
    import hashlib
    executable = backend_python()
    try:
        expected = hashlib.sha256((Path(__file__).resolve().parent / 'backends/triposr/uv.lock').read_bytes()).hexdigest()
        return executable.is_file() and (executable.parent.parent / '.backend-ready').read_text().strip() == expected
    except OSError:
        return False


def run_worker(command, folder, on_event, cancel, *, timeout=1200, env=None, grace=5):
    """Read structured progress without letting a silent process block cancellation."""
    import os
    import queue
    import signal
    import subprocess
    import threading
    import time
    from gpu_reservation import inherited_fds
    messages = queue.Queue()
    started = time.monotonic()
    failure = None
    with (Path(folder) / 'worker.log').open('w') as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, text=True,
                                   start_new_session=True, env=env, pass_fds=inherited_fds())

        def read_output():
            for line in process.stdout:
                messages.put(line)
            messages.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            while True:
                if cancel.is_set():
                    raise MeshCancelled('Mesh generation cancelled. Completed files are retained.')
                if time.monotonic() - started > timeout:
                    raise RuntimeError('Mesh generation timed out. Try a smaller mesh or texture.')
                try:
                    line = messages.get(timeout=.1)
                except queue.Empty:
                    continue
                if line is None:
                    break
                if not line.startswith('IDOL_EVENT '):
                    log.write(line)
                    continue
                try:
                    event = json.loads(line[len('IDOL_EVENT '):])
                except (TypeError, ValueError):
                    raise RuntimeError('Mesh worker returned invalid progress') from None
                if not isinstance(event, dict):
                    raise RuntimeError('Mesh worker returned invalid progress')
                if event.get('event') == 'error':
                    failure = str(event.get('message', 'Mesh generation failed'))[:1000]
                else:
                    on_event(event)
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                raise RuntimeError('Mesh worker did not exit after closing its output.') from None
            if cancel.is_set():
                raise MeshCancelled('Mesh generation cancelled. Completed files are retained.')
            if code or failure:
                raise RuntimeError(failure or f'Mesh worker failed with exit code {code}; see the local worker.log.')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            reader.join(timeout=2)
            process.stdout.close()


def generate_mesh(image_path, settings, on_event, cancel):
    import os
    root = Path(__file__).resolve().parent
    folder = Path(image_path).parent
    (folder / 'mesh-settings.json').write_text(json.dumps(settings))
    command = [str(backend_python()), str(root / 'backends/triposr/worker.py'),
               '--input', str(image_path), '--output', str(folder),
               '--models', str(root / 'models'), '--settings', str(folder / 'mesh-settings.json')]
    env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
           'U2NET_HOME': str(root / 'models/rembg'), 'OMP_NUM_THREADS': '4', 'PYTHONUNBUFFERED': '1'}
    run_worker(command, folder, on_event, cancel, env=env)
    details = validate_glb((folder / 'object.glb').read_bytes())
    details.update(json.loads((folder / 'mesh.json').read_text()))
    return details
