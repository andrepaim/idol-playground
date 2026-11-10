"""Check the isolated environment without loading model weights."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-marker', action='store_true')
    args = parser.parse_args()
    import torch
    import rembg  # noqa: F401
    import mcubes  # noqa: F401
    import xatlas  # noqa: F401
    import moderngl
    context = moderngl.create_context(standalone=True, backend='egl')
    report = {'torch': torch.__version__, 'cuda': torch.cuda.is_available(),
              'texture_renderer': context.info['GL_RENDERER'], 'surface': 'CPU PyMCubes'}
    context.release()
    if args.write_marker:
        lock = Path(__file__).with_name('uv.lock')
        (Path(sys.executable).parent.parent / '.backend-ready').write_text(hashlib.sha256(lock.read_bytes()).hexdigest())
    print(json.dumps(report))


if __name__ == '__main__':
    main()
