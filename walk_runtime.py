"""Isolated CPU walking jobs using the existing locked Blender environment."""

import hashlib
import json
import os
from pathlib import Path
import shutil
from mesh_runtime import run_worker
from rig_runtime import backend_python, backend_installed as backend_installed, validate_rigged_glb

ROOT = Path(__file__).resolve().parent
PHASES = ("walk_prepare", "walk_pose", "walk_bake", "walk_export", "walk_verify")
MESSAGES = (
    "Transferring continuous skin weights…",
    "Calibrating the reviewed canine stance…",
    "Solving four-beat paw contact…",
    "Exporting both walking clips…",
    "Reimporting and checking motion…",
)


def generate_walk(source, folder, settings, on_event, cancel):
    source = Path(source)
    folder = Path(folder)
    digests = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in ("rigged.glb", "skin.fbx")}
    shutil.copy2(source / "rigged.glb", folder / "input.glb")
    shutil.copy2(source / "skin.fbx", folder / "source.fbx")
    (folder / "walk-settings.json").write_text(json.dumps(settings, indent=2))
    env = {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "OMP_NUM_THREADS": "4",
        "PYTHONUNBUFFERED": "1",
        "CUDA_VISIBLE_DEVICES": "",
    }
    for phase, message in zip(PHASES, MESSAGES):
        on_event({"stage": phase, "message": message})
        phase_folder = folder / phase
        phase_folder.mkdir()
        run_worker(
            [str(backend_python()), str(ROOT / "backends/walking/worker.py"), "--phase", phase, "--job", str(folder)],
            phase_folder,
            on_event,
            cancel,
            timeout=600,
            env=env,
        )
    for name, digest in digests.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Source rig changed during animation")
    details = validate_rigged_glb((folder / "animated.glb").read_bytes())
    return {**details, **json.loads((folder / "walk.json").read_text())}
