"""Probe the isolated rigging environment without downloading or loading weights."""
import hashlib
import json
from pathlib import Path
import sys
import torch
import bpy
import flash_attn
import torch_scatter  # noqa: F401
import torch_cluster  # noqa: F401
import spconv.pytorch  # noqa: F401
import lightning  # noqa: F401
import pyrender  # noqa: F401

report = {'torch':torch.__version__,'cuda':torch.cuda.is_available(),'blender':bpy.app.version_string,
          'flash_attention':flash_attn.__version__}
if '--write-marker' in sys.argv:
    (Path(sys.executable).parent.parent/'.backend-ready').write_text(hashlib.sha256(Path(__file__).with_name('uv.lock').read_bytes()).hexdigest())
print(json.dumps(report))
