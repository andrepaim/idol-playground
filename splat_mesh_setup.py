"""Pinned public stereo source and weights for Idol-derived meshes."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parent
MODEL_ROOT=ROOT/'models/splat-mesh'
SOURCE_REVISION='560f3e8a2349aaad24fe9444ef1ca2770aeec5ab'
CHECKPOINT_SHA256='57e46b8fed66b685f732b730ebffd71998dcabea49f8443ca77e015419f6ae18'
CHECKPOINT_URL='https://github.com/David-Zhao-1997/High-frequency-Stereo-Matching-Network/releases/download/v1.0.0/DLNR_Middlebury.pth'


def models_ready():
    try:
        return (MODEL_ROOT/'source/.source-complete').read_text()==SOURCE_REVISION \
            and (MODEL_ROOT/'source/third_party/DLNR/core/dlnr.py').is_file() \
            and (MODEL_ROOT/'.download-complete').read_text()==CHECKPOINT_SHA256 \
            and (MODEL_ROOT/'DLNR_Middlebury.pth').stat().st_size>1000
    except OSError:return False


def ensure_models():
    MODEL_ROOT.mkdir(parents=True,exist_ok=True)
    source=MODEL_ROOT/'source';checkpoint=MODEL_ROOT/'DLNR_Middlebury.pth'
    if not source.exists():
        subprocess.run(['git','clone','--no-checkout','https://github.com/yanivw12/gs2mesh.git',str(source)],check=True)
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True).strip():
        raise RuntimeError('Stereo source has local edits; preserve them before rerunning setup.')
    subprocess.run(['git','-C',str(source),'fetch','origin',SOURCE_REVISION],check=True)
    subprocess.run(['git','-C',str(source),'checkout','--detach',SOURCE_REVISION],check=True)
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=SOURCE_REVISION:
        raise RuntimeError('Stereo source revision mismatch')
    (source/'.source-complete').write_text(SOURCE_REVISION)
    if not checkpoint.exists():
        temporary=checkpoint.with_suffix('.partial')
        request=urllib.request.Request(CHECKPOINT_URL,headers={'User-Agent':'idol-playground-model-setup'})
        with urllib.request.urlopen(request,timeout=120) as response,temporary.open('wb') as target:
            shutil.copyfileobj(response,target)
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=CHECKPOINT_SHA256:
            temporary.unlink(missing_ok=True)
            raise RuntimeError('Stereo checkpoint checksum mismatch')
        temporary.replace(checkpoint)
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=CHECKPOINT_SHA256:
        raise RuntimeError('Stereo checkpoint checksum mismatch. Preserve/move it aside before setup.')
    (MODEL_ROOT/'.download-complete').write_text(CHECKPOINT_SHA256)
    if not models_ready():raise RuntimeError('Stereo model setup is incomplete')
    return MODEL_ROOT


if __name__=='__main__':print('Splat mesh assets ready:',ensure_models())
