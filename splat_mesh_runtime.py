"""Bounded app orchestration for mesh reconstruction from an Idol splat."""
import hashlib
import json
import os
from pathlib import Path
import shutil

from mesh_runtime import run_worker,validate_glb,MeshCancelled

ROOT=Path(__file__).resolve().parent
IDOL_STAGES=('load','preprocess','encode','sampling','decode','save')
CONVERT_STAGES=('capture','stereo','surface','export')
BASE={'load':10,'preprocess':2,'encode':12,'sampling':45,'decode':3,'save':1,
      'capture':330,'stereo':30,'surface':5,'export':2}


def backend_python():
    return Path(os.environ.get('IDOL_STEREO_PYTHON',str(ROOT/'.venv-stereo/bin/python')))


def idol_python():
    return Path(os.environ.get('IDOL_MODEL_PYTHON',str(ROOT/'.venv/bin/python')))


def idol_installed():
    interpreter=idol_python()
    return interpreter.is_file() and any((interpreter.parent.parent/'lib').glob('python*/site-packages/idol/__init__.py'))


def backend_installed():
    interpreter=backend_python()
    try:
        return interpreter.is_file() and (interpreter.parent.parent/'.backend-ready').read_text().strip() \
            ==hashlib.sha256((ROOT/'experiments/splat_mesh/uv.lock').read_bytes()).hexdigest() \
            and (ROOT/'node_modules/@mkkellogg/gaussian-splats-3d/build/gaussian-splats-3d.module.js').is_file()
    except OSError:return False


def stage_config(settings,*,upload=False):
    stages=IDOL_STAGES+CONVERT_STAGES if upload else CONVERT_STAGES
    count=settings.get('num_gaussians',262144)
    scales={stage:1 for stage in stages}
    scales['capture']=max(.25,count/262144)
    scales['surface']=1 if settings['surface_quality']=='fine' else .125
    if upload:scales['sampling']=settings.get('steps',50)/50
    return stages,{key:BASE[key] for key in stages},scales


def generate_splat_mesh(splat_path,folder,settings,on_event,cancel,*,image_path=None):
    folder=Path(folder)
    (folder/'mesh-settings.json').write_text(json.dumps(settings,indent=2))
    target=folder/'source.ply'
    if splat_path is not None:
        if Path(splat_path).resolve()!=target.resolve():shutil.copy2(splat_path,target)
        prepared=Path(splat_path).parent/'prepared.png'
        if prepared.is_file():shutil.copy2(prepared,folder/'prepared.png')
    environment={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'4','PYTHONUNBUFFERED':'1'}
    def phase(name,python,script,arguments,timeout):
        if cancel.is_set():raise MeshCancelled('Mesh generation cancelled. The original splat is preserved.')
        logs=folder/name;logs.mkdir()
        run_worker([str(python),str(ROOT/script),*arguments],logs,on_event,cancel,timeout=timeout,env=environment,grace=10)
    if image_path is not None:
        phase('idol',idol_python(),'backends/splat_mesh/idol_worker.py',
              ['--input',str(image_path),'--job',str(folder)],600)
    for name,message in [('capture','Rendering calibrated views of your splat…'),
                         ('stereo','Recovering the surface depth from stereo views…'),
                         ('surface','Fusing depth and cleaning the mesh…'),
                         ('export','Checking geometry and embedded colors…')]:
        on_event({'stage':name,'message':message})
        phase(name,backend_python(),'backends/splat_mesh/worker.py',
              ['--phase',name,'--job',str(folder),'--models',str(ROOT/'models/splat-mesh')],3600 if name=='capture' else 600)
    details=validate_glb((folder/'object.glb').read_bytes())
    details.update(json.loads((folder/'mesh.json').read_text()))
    return details
