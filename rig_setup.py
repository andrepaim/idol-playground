"""Pinned public UniRig assets, separate from reconstruction environments."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
from huggingface_hub import snapshot_download

MODEL_ROOT = Path(__file__).resolve().parent / 'models'
SOURCE_REVISION = '6793c6640ff01c8fb389f3993434124bb43d2933'
SOURCES = {
    'unirig': {'repo':'VAST-AI/UniRig','revision':'36842e2b5947e9e60f89275b83208c8e74071c63',
               'required':['skeleton/articulation-xl_quantization_256/model.ckpt','skin/articulation-xl/model.ckpt']},
    'unirig-opt': {'repo':'facebook/opt-350m','revision':'08ab08cc4b72ff5593870b5d527cf4230323703c', 'required':['config.json']},
}


def models_ready():
    try:
        return all((MODEL_ROOT/name/'.download-complete').read_text() == item['revision']
                   and all((MODEL_ROOT/name/file).is_file() for file in item['required']) for name,item in SOURCES.items()) \
            and (MODEL_ROOT/'unirig-source/.source-complete').read_text() == SOURCE_REVISION \
            and (MODEL_ROOT/'unirig-source/run.py').is_file()
    except OSError:return False


def download(name):
    item = SOURCES[name];folder = MODEL_ROOT/name
    snapshot_download(item['repo'],revision=item['revision'],allow_patterns=item['required']+['README.md','LICENSE*'],
                      local_dir=folder,token=False,max_workers=2)
    (folder/'.download-complete').write_text(item['revision'])


def source():
    folder = MODEL_ROOT/'unirig-source'
    if (folder/'.git').is_dir():
        subprocess.run(['git','-C',str(folder),'fetch','origin',SOURCE_REVISION],check=True)
    elif folder.exists():raise RuntimeError('Incomplete UniRig source directory; move it aside before setup')
    else:subprocess.run(['git','clone','--filter=blob:none','--no-checkout','https://github.com/VAST-AI-Research/UniRig.git',str(folder)],check=True)
    subprocess.run(['git','-C',str(folder),'checkout','--detach',SOURCE_REVISION],check=True)
    if subprocess.check_output(['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip() != SOURCE_REVISION:
        raise RuntimeError('UniRig source revision mismatch')
    (folder/'.source-complete').write_text(SOURCE_REVISION)


def ensure_models():
    MODEL_ROOT.mkdir(exist_ok=True)
    if not models_ready():
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(download,name) for name in SOURCES]+[pool.submit(source)]
            for future in futures:future.result()
    if not models_ready():raise RuntimeError('Rigging assets are incomplete')
    return MODEL_ROOT


if __name__ == '__main__':print('Rigging assets ready:',ensure_models())
