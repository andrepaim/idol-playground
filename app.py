"""Local web server. The model is loaded lazily, once, in a single worker."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import gc
from importlib.util import find_spec
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from model_setup import ensure_models, models_ready
from progress import GenerationProgress, instrument_pipeline
from mesh_setup import ensure_models as ensure_mesh_models, models_ready as mesh_models_ready
from mesh_runtime import backend_installed as mesh_backend_installed, generate_mesh, MeshCancelled
from mesh_progress import MeshProgress
from rig_runtime import backend_installed as rig_backend_installed, generate_rig, PHASES as RIG_PHASES
from rig_setup import models_ready as rig_models_ready
from splat_mesh_runtime import backend_installed as splat_backend_installed, idol_installed as splat_idol_installed, generate_splat_mesh, stage_config
from splat_mesh_setup import models_ready as splat_models_ready

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)
MAX_UPLOAD = 20 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000
@asynccontextmanager
async def lifespan(app):
    yield
    for event in list(mesh_cancellations.values()):
        event.set()
    executor.shutdown(wait=True, cancel_futures=True)


app = FastAPI(title="Idol Playground", lifespan=lifespan)
executor = ThreadPoolExecutor(max_workers=1)
lock = threading.Lock()
jobs: dict[str, dict] = {}
pipeline = None
active_job = None
job_progress = {}
mesh_cancellations = {}


@app.get("/api/status")
def status():
    installed = find_spec("idol") is not None
    return {
        "splat_mesh": {"ready": splat_backend_installed(), "weights_downloaded": splat_models_ready(),
                       "upload_ready": splat_idol_installed() and models_ready()},
        "rig": {"ready": rig_backend_installed(), "weights_downloaded": rig_models_ready()},
        "backend": "local",
        "model_installed": installed,
        "ready": installed,
        "weights_downloaded": models_ready(),
        "model_loaded": pipeline is not None,
        "active_job": active_job,
        "mesh": {"backend": "triposr", "ready": mesh_backend_installed(),
                 "weights_downloaded": mesh_models_ready()},
    }


def update(job_id: str, **values):
    with lock:
        jobs[job_id].update(values)


def gpu():
    """The torch device module for the best accelerator: CUDA, else Apple Silicon MPS."""
    import torch
    if torch.cuda.is_available():
        return "cuda", torch.cuda
    if torch.backends.mps.is_available():
        return "mps", torch.mps
    return None, None


def generate(job_id: str, image_path: Path, settings: dict):
    global pipeline, active_job
    started = time.monotonic()
    folder = image_path.parent
    try:
        progress = GenerationProgress(
            settings, lambda **values: update(job_id, **values), OUTPUTS / ".timings.json",
            cold=pipeline is None, optimize=os.environ.get("IDOL_OPTIMIZE", "0") == "1",
        )
        with lock:
            job_progress[job_id] = progress
        from idol import IdolPipeline

        device, accel = gpu()
        if device is None:
            raise RuntimeError("No GPU available. Use an NVIDIA CUDA GPU or an Apple Silicon Mac (MPS).")
        if pipeline is None:
            if not models_ready():
                progress.start("download", "Downloading model files. ETA will be available once the download finishes…")
            weights, encoders = ensure_models()
            progress.start("load")
            pipeline = IdolPipeline.from_pretrained(
                weights, device=device, image_encoders=encoders,
                optimize=os.environ.get("IDOL_OPTIMIZE", "0") == "1",
            )
        with instrument_pipeline(pipeline, progress, accel.synchronize):
            output = pipeline(str(image_path), **settings)
        progress.start("save")
        output.gaussian.save_ply(str(folder / "object.ply"))
        output.preprocessed_image.save(folder / "prepared.png")
        (folder / "camera.json").write_text(json.dumps(output.camera, indent=2))
        (folder / "settings.json").write_text(json.dumps(settings, indent=2))
        files = {name: f"/outputs/{job_id}/{name}" for name in (
            "object.ply", "prepared.png", "camera.json", "settings.json"
        ) if (folder / name).exists()}
        timing = progress.finish()
        update(job_id, state="complete", stage="complete", eta_seconds=0, message="Your 3D object is ready.", files=files,
               seconds=round(time.monotonic() - started, 1), **timing)
        try:
            (folder / "job.json").write_text(json.dumps(jobs[job_id], indent=2))
        except OSError:
            logging.warning("Could not save job metadata", exc_info=True)
    except Exception as exc:
        logging.exception("Idol generation failed")
        message = str(exc)
        if "out of memory" in message.lower():
            message = "GPU ran out of memory. Close other GPU apps, lower the Gaussian count, and try again."
        elif any(word in message.lower() for word in ("gated", "401", "403", "access to model")):
            message = "Could not download model files from Hugging Face. Run uv run --no-sync python model_setup.py in the terminal for details."
        update(job_id, state="error", stage="error", eta_seconds=None, message=message[:1500])
    finally:
        try:
            _, accel = gpu()
            if accel is not None:
                accel.empty_cache()
        except Exception:
            logging.debug("GPU cleanup unavailable", exc_info=True)
        finally:
            with lock:
                active_job = None
                job_progress.pop(job_id, None)


def release_idol():
    """Release all cached Idol tensors before the separate mesh CUDA process starts."""
    global pipeline
    if pipeline is not None:
        pipeline = None
        gc.collect()
        import torch
        torch.cuda.empty_cache()


def generate_mesh_job(job_id: str, image_path: Path, settings: dict):
    global active_job
    started = time.monotonic()
    folder = image_path.parent
    cancellation = mesh_cancellations[job_id]
    try:
        release_idol()
        progress = MeshProgress(settings, lambda **values: update(job_id, **values), OUTPUTS / '.mesh-timings.json')
        with lock:
            job_progress[job_id] = progress
        if not mesh_models_ready():
            update(job_id, stage='download', message='Downloading mesh model files…', eta_seconds=None)
            ensure_mesh_models()
        if cancellation.is_set():
            raise MeshCancelled('Mesh generation cancelled.')
        details = generate_mesh(image_path, settings, progress.event, cancellation)
        files = {name: f'/outputs/{job_id}/{name}' for name in
                 ('object.glb', 'prepared.png', 'texture.png', 'source-mesh.glb', 'mesh.json', 'mesh-settings.json')
                 if (folder / name).is_file()}
        timing = progress.finish()
        update(job_id, state='complete', stage='complete', eta_seconds=0, message='Your textured mesh is ready.',
               files=files, mesh=details, seconds=round(time.monotonic() - started, 1), **timing)
    except MeshCancelled as error:
        update(job_id, state='cancelled', stage='cancelled', eta_seconds=None, message=str(error))
    except Exception as error:
        logging.exception('Mesh generation failed')
        update(job_id, state='error', stage='error', eta_seconds=None, message=str(error)[:1500])
    finally:
        try:
            (folder / 'job.json').write_text(json.dumps(jobs[job_id], indent=2))
        except OSError:
            logging.warning('Could not save mesh job metadata', exc_info=True)
        with lock:
            active_job = None
            job_progress.pop(job_id, None)
            mesh_cancellations.pop(job_id, None)


def generate_rig_job(job_id: str, source: Path, seed: int):
    global active_job
    folder = OUTPUTS / job_id
    started = time.monotonic()
    try:
        release_idol()
        progress = MeshProgress({}, lambda **values: update(job_id, **values), OUTPUTS / '.rig-timings.json',
                                stages=RIG_PHASES, baseline=dict(zip(RIG_PHASES, (4,30,4,30,8,8))), scales={})
        with lock:
            job_progress[job_id] = progress
        details = generate_rig(source, folder, seed, progress.event, mesh_cancellations[job_id])
        files = {name: f'/outputs/{job_id}/{name}' for name in
                 ('rigged.glb','rigged.fbx','character.blend','rig.json') if (folder/name).is_file()}
        timing = progress.finish()
        update(job_id, state='complete', stage='complete', eta_seconds=0,
               message='Your experimental rig is ready. Inspect the skeleton and bend before game use.',
               rig=details, files=files, seconds=round(time.monotonic()-started,1), **timing)
    except MeshCancelled:
        update(job_id,state='cancelled',stage='cancelled',eta_seconds=None,message='Automatic rigging cancelled. The static mesh is preserved.')
    except Exception as error:
        logging.exception('Automatic rigging failed')
        update(job_id,state='error',stage='error',eta_seconds=None,message=str(error)[:1500])
    finally:
        try:
            (folder/'job.json').write_text(json.dumps(jobs[job_id],indent=2))
        except OSError:
            logging.warning('Could not save rig metadata',exc_info=True)
        with lock:
            active_job = None
            job_progress.pop(job_id,None)
            mesh_cancellations.pop(job_id,None)


def generate_splat_mesh_job(job_id: str, source: Path | None, settings: dict, image_path: Path | None = None):
    global active_job
    folder = OUTPUTS/job_id
    started = time.monotonic()
    try:
        release_idol()
        stages,baseline,scales = stage_config(settings,upload=image_path is not None)
        progress = MeshProgress(settings,lambda **values:update(job_id,**values),OUTPUTS/'.splat-mesh-timings.json',
                                stages=stages,baseline=baseline,scales=scales)
        with lock:
            job_progress[job_id] = progress
        details = generate_splat_mesh(source,folder,settings,progress.event,mesh_cancellations[job_id],image_path=image_path)
        files = {name:f'/outputs/{job_id}/{name}' for name in
                 ('object.glb','source.ply','raw-mesh.ply','mesh.json','mesh-settings.json','prepared.png') if (folder/name).is_file()}
        timing = progress.finish()
        update(job_id,state='complete',stage='complete',eta_seconds=0,message='Your splat-derived mesh is ready.',
               files=files,mesh=details,seconds=round(time.monotonic()-started,1),**timing)
    except MeshCancelled:
        update(job_id,state='cancelled',stage='cancelled',eta_seconds=None,message='Mesh generation cancelled. Original files are preserved.')
    except Exception as error:
        logging.exception('Splat-derived mesh generation failed')
        update(job_id,state='error',stage='error',eta_seconds=None,message=str(error)[:1500])
    finally:
        try:
            (folder/'job.json').write_text(json.dumps(jobs[job_id],indent=2))
        except OSError:
            logging.warning('Could not save splat mesh metadata',exc_info=True)
        with lock:
            active_job = None
            job_progress.pop(job_id,None)
            mesh_cancellations.pop(job_id,None)


def require_splat_setup(*,upload=False):
    if not splat_backend_installed() or not splat_models_ready():
        raise HTTPException(503,'Splat-derived mesh setup is incomplete. Run make setup-splat-mesh splat-mesh-models.')
    if upload and (not splat_idol_installed() or not models_ready()):
        raise HTTPException(503,'Image-to-mesh also needs Idol. Run make setup-local models.')


@app.post('/api/jobs/{source_id}/mesh', status_code=202)
def convert_splat(source_id: str, surface_quality: Literal['fine','balanced'] = Form('fine'),
                  component_mode: Literal['largest','all'] = Form('largest')):
    global active_job
    if len(source_id)!=32 or any(c not in '0123456789abcdef' for c in source_id):
        raise HTTPException(404,'Splat generation not found.')
    source_job = get_job(source_id)
    source = OUTPUTS/source_id/'object.ply'
    if source_job['state']!='complete' or source_job.get('output_type','splat')!='splat' or not source.is_file():
        raise HTTPException(409,'Complete an Idol splat generation before creating a mesh.')
    require_splat_setup()
    settings = {'surface_quality':surface_quality,'component_mode':component_mode,
                'seed':source_job.get('settings',{}).get('seed',42),
                'num_gaussians':source_job.get('settings',{}).get('num_gaussians',262144)}
    if settings['num_gaussians'] not in (65536,131072,262144,524288,1048576):
        raise HTTPException(422,'Unsupported source Gaussian count.')
    job_id = uuid4().hex
    with lock:
        if active_job:raise HTTPException(409,'A generation is already running. Wait for it to finish.')
        (OUTPUTS/job_id).mkdir()
        jobs[job_id] = {'id':job_id,'state':'running','stage':'starting','eta_seconds':None,'started_at':time.time(),
                        'message':'Starting splat-to-mesh conversion…','output_type':'mesh','mesh_backend':'idol',
                        'settings':settings,'source_job':source_id}
        mesh_cancellations[job_id] = threading.Event()
        active_job = job_id
        try:executor.submit(generate_splat_mesh_job,job_id,source,settings)
        except Exception:
            active_job = None
            mesh_cancellations.pop(job_id,None)
            jobs.pop(job_id,None)
            raise
    return {'id':job_id}


@app.post('/api/jobs/{source_id}/rig', status_code=202)
def create_rig(source_id: str):
    global active_job
    if len(source_id) != 32 or any(c not in '0123456789abcdef' for c in source_id):
        raise HTTPException(404,'Mesh generation not found.')
    source_job = get_job(source_id)
    source = OUTPUTS/source_id/'object.glb'
    if source_job.get('output_type') != 'mesh' or source_job['state'] != 'complete' or not source.is_file():
        raise HTTPException(409,'Complete a mesh generation before automatic rigging.')
    if not rig_backend_installed() or not rig_models_ready():
        raise HTTPException(503,'Rigging setup is incomplete. Run make setup-rig rig-models.')
    seed = source_job.get('settings',{}).get('seed',42)
    if not isinstance(seed,int) or not 0 <= seed <= 2**31-1:
        raise HTTPException(422,'Invalid source seed.')
    job_id = uuid4().hex
    with lock:
        if active_job:
            raise HTTPException(409,'A generation is already running. Wait for it to finish.')
        (OUTPUTS/job_id).mkdir()
        jobs[job_id] = {'id':job_id,'state':'running','stage':'starting','eta_seconds':None,
                        'started_at':time.time(),'message':'Starting automatic rigging…','settings':{'seed':seed},
                        'output_type':'rig','source_job':source_id}
        mesh_cancellations[job_id] = threading.Event()
        active_job = job_id
        try:
            executor.submit(generate_rig_job,job_id,source,seed)
        except Exception:
            active_job = None
            mesh_cancellations.pop(job_id,None)
            jobs.pop(job_id,None)
            raise
    return {'id':job_id}


@app.post("/api/generate", status_code=202)
async def create_job(
    image: UploadFile = File(...),
    mode: Literal["real", "synthetic"] = Form("real"),
    output_type: Literal["splat", "mesh"] = Form("splat"),
    mesh_backend: Literal['triposr','idol'] = Form('triposr'),
    surface_quality: Literal['fine','balanced'] = Form('fine'),
    component_mode: Literal['largest','all'] = Form('largest'),
    mesh_resolution: int = Form(192),
    texture_resolution: int = Form(1024),
    target_faces: int = Form(25000),
    steps: int = Form(50, ge=10, le=100),
    seed: int = Form(42, ge=0, le=2**31 - 1),
    num_gaussians: int = Form(262144),
    cfg_strength: float = Form(3.0, ge=0, le=10),
    rescale_t: float = Form(3.0, ge=1, le=6),
):
    global active_job
    if num_gaussians not in (65536, 131072, 262144, 524288, 1048576):
        raise HTTPException(422, "Choose a supported Gaussian count.")
    if output_type == 'mesh' and mesh_backend == 'idol':
        require_splat_setup(upload=True)
    elif output_type == 'mesh':
        if mesh_resolution not in (128, 192, 256) or texture_resolution not in (512, 1024, 2048) or target_faces not in (10000, 25000, 50000, 100000):
            raise HTTPException(422, 'Choose supported mesh, triangle and texture settings.')
        if not status().get('mesh', {}).get('ready'):
            raise HTTPException(503, 'Mesh setup is incomplete. Run make setup-mesh mesh-models. See README.md.')
    elif not status()["ready"]:
        raise HTTPException(503, "Local setup is incomplete. Install the local model dependencies with uv sync --extra local. See README.md.")
    data = await image.read(MAX_UPLOAD + 1)
    await image.close()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Image must be 20 MB or smaller.")
    try:
        with Image.open(BytesIO(data)) as uploaded:
            if uploaded.format not in ("PNG", "JPEG", "WEBP"):
                raise HTTPException(422, "Upload a PNG, JPEG, or WebP image.")
            if uploaded.width * uploaded.height > Image.MAX_IMAGE_PIXELS:
                raise HTTPException(413, "Image must be 25 megapixels or smaller.")
            prepared = ImageOps.exif_transpose(uploaded).convert("RGBA")
            prepared.thumbnail((2048, 2048))
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "Upload a valid PNG, JPEG, or WebP image.") from None
    settings = dict(mode=mode, steps=steps, seed=seed, num_gaussians=num_gaussians,
                    cfg_strength=cfg_strength, rescale_t=rescale_t)
    if output_type == 'mesh' and mesh_backend == 'idol':
        settings.update(surface_quality=surface_quality,component_mode=component_mode)
    elif output_type == 'mesh':
        settings = dict(mesh_resolution=mesh_resolution, texture_resolution=texture_resolution,
                        target_faces=target_faces, seed=seed)
    job_id = uuid4().hex
    folder = OUTPUTS / job_id
    with lock:
        if active_job:
            raise HTTPException(409, "A generation is already running. Wait for it to finish.")
        folder.mkdir()
        prepared.save(folder / "input.png")
        jobs[job_id] = {"id": job_id, "state": "running", "stage": "starting", "eta_seconds": None,
                        "started_at": time.time(), "message": "Starting…", "settings": settings, "output_type": output_type, "mesh_backend": mesh_backend if output_type == "mesh" else None}
        active_job = job_id
        try:
            if output_type == 'mesh':
                mesh_cancellations[job_id] = threading.Event()
            if output_type == 'mesh' and mesh_backend == 'idol':
                executor.submit(generate_splat_mesh_job,job_id,None,settings,folder/'input.png')
            else:
                executor.submit(generate_mesh_job if output_type == 'mesh' else generate, job_id, folder / "input.png", settings)
        except Exception:
            active_job = None
            jobs.pop(job_id, None)
            mesh_cancellations.pop(job_id, None)
            raise
    return {"id": job_id}


@app.get('/api/jobs')
def recent_jobs(limit: int = Query(50,ge=1,le=50)):
    with lock:
        snapshots = {key:dict(value) for key,value in jobs.items()}
    for folder in OUTPUTS.iterdir():
        if not folder.is_dir() or len(folder.name)!=32 or any(c not in '0123456789abcdef' for c in folder.name):continue
        if folder.name in snapshots:continue
        try:snapshots[folder.name] = json.loads((folder/'job.json').read_text())
        except (OSError,ValueError):continue
    summaries = []
    for key,job in snapshots.items():
        if not isinstance(job,dict) or job.get('state')!='complete':continue
        kind = job.get('output_type','splat')
        filename = 'rigged.glb' if kind=='rig' else 'object.glb' if kind=='mesh' else 'object.ply'
        if not (OUTPUTS/key/filename).is_file():continue
        started = job.get('started_at',0)
        if not isinstance(started,(int,float)):started = 0
        summaries.append({'id':key,'state':'complete','output_type':kind,'mesh_backend':job.get('mesh_backend'),
                          'started_at':started,'seconds':job.get('seconds')})
    return {'jobs':sorted(summaries,key=lambda job:job['started_at'],reverse=True)[:limit]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with lock:
        if job_id not in jobs:
            if len(job_id) == 32 and all(c in "0123456789abcdef" for c in job_id):
                try:
                    return json.loads((OUTPUTS / job_id / "job.json").read_text())
                except (OSError, ValueError):
                    pass
            raise HTTPException(404, "Generation not found. Saved files remain in outputs/.")
        job = dict(jobs[job_id])
        if job["state"] == "running":
            job["elapsed_seconds"] = round(time.time() - job["started_at"], 1)
            if job_id in job_progress:
                job.update(job_progress[job_id].snapshot())
        return job


@app.post('/api/jobs/{job_id}/cancel', status_code=202)
def cancel_mesh(job_id: str):
    with lock:
        if job_id not in jobs:
            raise HTTPException(404, 'Generation not found.')
        if jobs[job_id]['state'] != 'running':
            raise HTTPException(409, 'This generation is no longer running.')
        event = mesh_cancellations.get(job_id)
        if event is None:
            raise HTTPException(409, 'Cancellation is available for mesh and rigging jobs only.')
        event.set()
        jobs[job_id]['message'] = 'Stopping the generation worker…'
    return {'id': job_id, 'state': 'cancelling'}


app.mount("/outputs", StaticFiles(directory=OUTPUTS), name="outputs")
if (ROOT / "dist").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="web")
