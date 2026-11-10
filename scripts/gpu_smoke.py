"""Deliberate real inference with synthetic input and disposable output storage."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from uuid import uuid4


def validate_ply(data, expected_count):
    marker = b'end_header\n'
    if not data.startswith(b'ply\n') or marker not in data:
        raise ValueError('Missing PLY header')
    header, body = data.split(marker, 1)
    lines = header.decode('ascii').splitlines()
    if 'format binary_little_endian 1.0' not in lines:
        raise ValueError('Expected binary little-endian PLY')
    count = None
    stride = 0
    scalar_sizes = {'float': 4, 'float32': 4, 'double': 8, 'uchar': 1, 'uint8': 1, 'int': 4}
    vertex = False
    for line in lines:
        parts = line.split()
        if parts[:1] == ['element']:
            vertex = parts[1] == 'vertex'
            if vertex:
                count = int(parts[2])
        elif vertex and parts[:1] == ['property']:
            stride += scalar_sizes[parts[1]]
    if count != expected_count or not stride or len(body) != count * stride:
        raise ValueError('PLY record count or byte length mismatch')
    # Reject invalid float positions, rather than accepting a header alone.
    for offset in range(0, len(body), stride):
        if stride >= 12:
            import math
            if not all(math.isfinite(value) for value in struct.unpack_from('<fff', body, offset)):
                raise ValueError('Non-finite vertex position')
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    import app as server
    from model_setup import models_ready, SOURCES
    from PIL import Image, ImageDraw
    import torch
    if not models_ready():
        raise SystemExit('Download pinned models first; smoke tests never download models implicitly.')
    if not torch.cuda.is_available():
        raise SystemExit('CUDA unavailable')
    settings = dict(mode='synthetic', steps=10, seed=42, num_gaussians=65536, cfg_strength=3.0, rescale_t=3.0)
    with tempfile.TemporaryDirectory(prefix='idol-gpu-smoke-') as directory:
        folder = Path(directory)
        image = Image.new('RGB', (256, 256), 'white')
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((65, 40, 190, 210), radius=20, fill='royalblue')
        draw.rectangle((90, 25, 165, 50), fill='navy')
        image.save(folder / 'input.png')
        job_id = uuid4().hex
        server.OUTPUTS = folder
        server.jobs[job_id] = {'id': job_id, 'state': 'running', 'settings': settings}
        torch.cuda.reset_peak_memory_stats()
        server.generate(job_id, folder / 'input.png', settings)
        result = server.jobs[job_id]
        if result['state'] != 'complete':
            raise SystemExit(result.get('message', 'Inference failed'))
        count = validate_ply((folder / 'object.ply').read_bytes(), 65536)
        receipt = {
            'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'tracked_changes': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=root)),
            'gpu': torch.cuda.get_device_name(0), 'torch': torch.__version__, 'cuda': torch.version.cuda,
            'driver': subprocess.check_output(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'], text=True).strip(),
            'settings': settings, 'models': {key: value['revision'] for key, value in SOURCES.items()},
            'vertex_count': count, 'seconds': result['seconds'], 'stage_seconds': result['stage_seconds'],
            'peak_allocated_mib': round(torch.cuda.max_memory_allocated() / 2**20),
            'limitation': 'Synthetic input checks successful inference and PLY integrity; no character or visual-quality claim.',
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
