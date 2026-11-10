"""Read-only environment diagnostics; never install packages or download weights."""
import argparse
from importlib.util import find_spec
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-gpu', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from model_setup import models_ready
    from mesh_setup import models_ready as mesh_models_ready
    from mesh_runtime import backend_installed
    report = {'python': sys.version.split()[0], 'interpreter': sys.executable,
              'node': shutil.which('node') is not None, 'uv': shutil.which('uv') is not None,
              'frontend_built': (root / 'dist/index.html').is_file(),
              'idol_installed': find_spec('idol') is not None, 'models_ready': models_ready(),
              'disk_free_gib': round(shutil.disk_usage(root).free / 2**30, 1), 'cuda': False}
    if find_spec('torch'):
        import torch
        report['torch'] = torch.__version__
        report['cuda'] = torch.cuda.is_available()
        if report['cuda']:
            report['gpu'] = torch.cuda.get_device_name(0)
    if shutil.which('nvidia-smi'):
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,driver_version',
                                 '--format=csv,noheader'], capture_output=True, text=True)
        report['nvidia_smi'] = result.stdout.strip() if result.returncode == 0 else 'unavailable'
    report['mesh'] = {'environment_installed': backend_installed(), 'models_ready': mesh_models_ready()}
    from rig_runtime import backend_installed as rig_installed
    from rig_setup import models_ready as rig_ready
    report['rig'] = {'environment_installed': rig_installed(), 'models_ready': rig_ready()}
    report['generation_ready'] = all(report[key] for key in ('cuda', 'idol_installed', 'models_ready', 'frontend_built'))
    report['next_step'] = 'make run' if report['generation_ready'] else 'For generation: make setup-local models; npm run build. See docs/getting-started.md.'
    print(json.dumps(report, indent=2))
    return int(args.require_gpu and not report['generation_ready'])


if __name__ == '__main__':
    raise SystemExit(main())
