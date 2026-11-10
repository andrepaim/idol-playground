"""Pinned public TripoSR assets, independent from Idol's environment and downloads."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import urllib.request

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent
MODEL_ROOT = ROOT / 'models'
SOURCE_REVISION = '107cefdc244c39106fa830359024f6a2f1c78871'
SOURCE_URL = 'https://github.com/VAST-AI-Research/TripoSR.git'
SOURCES = {
    'triposr': {'repo': 'stabilityai/TripoSR', 'revision': '5b521936b01fbe1890f6f9baed0254ab6351c04a',
                'required': ['config.yaml', 'model.ckpt'], 'files': ['config.yaml', 'model.ckpt', 'README.md', 'LICENSE*']},
    'triposr-dino': {'repo': 'facebook/dino-vitb16', 'revision': 'f205d5d8e640a89a2b8ef0369670dfc37cc07fc2',
                     'required': ['config.json'], 'files': ['config.json', 'README.md', 'LICENSE*']},
}
BACKGROUND_URL = 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx'
BACKGROUND_MD5 = '60024c5c889badc19c04ad937298a77b'  # Published by rembg's pinned U2netSession.


def models_ready():
    try:
        return all(
            (MODEL_ROOT / name / '.download-complete').read_text() == source['revision']
            and all((MODEL_ROOT / name / path).is_file() for path in source['required'])
            for name, source in SOURCES.items()
        ) and (MODEL_ROOT / 'triposr-source/.source-complete').read_text() == SOURCE_REVISION \
            and (MODEL_ROOT / 'triposr-source/tsr/system.py').is_file() \
            and (MODEL_ROOT / 'rembg/u2net.onnx').is_file()
    except (OSError, ValueError):
        return False


def download_snapshot(name):
    source = SOURCES[name]
    directory = MODEL_ROOT / name
    print('Downloading', source['repo'], flush=True)
    snapshot_download(source['repo'], revision=source['revision'], allow_patterns=source['files'],
                      local_dir=directory, token=False, max_workers=3)
    (directory / '.download-complete').write_text(source['revision'])


def download_source():
    directory = MODEL_ROOT / 'triposr-source'
    if (directory / '.git').is_dir():
        subprocess.run(['git', '-C', str(directory), 'fetch', 'origin', SOURCE_REVISION], check=True)
    else:
        if directory.exists():
            raise RuntimeError('Incomplete TripoSR source directory; move it aside before retrying setup.')
        subprocess.run(['git', 'clone', '--filter=blob:none', '--no-checkout', SOURCE_URL, str(directory)], check=True)
    subprocess.run(['git', '-C', str(directory), 'checkout', '--detach', SOURCE_REVISION], check=True)
    actual = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != SOURCE_REVISION:
        raise RuntimeError('TripoSR source revision mismatch')
    (directory / '.source-complete').write_text(SOURCE_REVISION)


def download_background():
    target = MODEL_ROOT / 'rembg/u2net.onnx'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and hashlib.md5(target.read_bytes()).hexdigest() == BACKGROUND_MD5:
        return
    temporary = target.with_suffix('.partial')
    request = urllib.request.Request(BACKGROUND_URL, headers={'User-Agent': 'idol-playground-model-setup'})
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as output:
        shutil.copyfileobj(response, output)
    if hashlib.md5(temporary.read_bytes()).hexdigest() != BACKGROUND_MD5:
        temporary.unlink(missing_ok=True)
        raise RuntimeError('Background model checksum mismatch')
    temporary.replace(target)


def ensure_models():
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    if not models_ready():
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(download_snapshot, name) for name in SOURCES]
            futures.extend([pool.submit(download_source), pool.submit(download_background)])
            for future in futures:
                future.result()
    if not models_ready():
        raise RuntimeError('Mesh model setup incomplete')
    return MODEL_ROOT


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print('Mesh assets ready:', ensure_models())
