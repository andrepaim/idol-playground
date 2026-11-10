"""Check the isolated runtime, Chromium and browser assets without loading model weights."""
import hashlib
import json
from pathlib import Path
import sys
import torch
import cv2  # noqa: F401
import open3d  # noqa: F401
import psutil  # noqa: F401
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[2]
if not (root/'node_modules/@mkkellogg/gaussian-splats-3d/build/gaussian-splats-3d.module.js').is_file():
    raise SystemExit('Run npm ci before setting up mesh capture.')
with sync_playwright() as p:
    browser=p.chromium.launch(args=['--no-sandbox','--enable-unsafe-swiftshader'])
    browser.close()
print(json.dumps({'torch':torch.__version__,'cuda':torch.cuda.is_available(),'chromium':'ready'}))
if '--write-marker' in sys.argv:
    (Path(sys.executable).parent.parent/'.backend-ready').write_text(hashlib.sha256((root/'experiments/splat_mesh/uv.lock').read_bytes()).hexdigest())
