"""Local web server. The model is loaded lazily, once, in a single worker."""

from concurrent.futures import ThreadPoolExecutor
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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from model_setup import ensure_models, models_ready
from progress import GenerationProgress, instrument_pipeline

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)
MAX_UPLOAD = 20 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000
app = FastAPI(title="Idol Playground")
executor = ThreadPoolExecutor(max_workers=1)
lock = threading.Lock()
jobs: dict[str, dict] = {}
pipeline = None
active_job = None
job_progress = {}


@app.get("/api/status")
def status():
    installed = find_spec("idol") is not None
    return {
        "backend": "local",
        "model_installed": installed,
        "ready": installed,
        "weights_downloaded": models_ready(),
        "model_loaded": pipeline is not None,
        "active_job": active_job,
    }


def update(job_id: str, **values):
    with lock:
        jobs[job_id].update(values)


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
        import torch
        from idol import IdolPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable. Install a CUDA-enabled PyTorch build and check nvidia-smi.")
        if pipeline is None:
            if not models_ready():
                progress.start("download", "Downloading model files. ETA will be available once the download finishes…")
            weights, encoders = ensure_models()
            progress.start("load")
            pipeline = IdolPipeline.from_pretrained(
                weights, device="cuda", image_encoders=encoders,
                optimize=os.environ.get("IDOL_OPTIMIZE", "0") == "1",
            )
        with instrument_pipeline(pipeline, progress, torch.cuda.synchronize):
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
            import torch
            torch.cuda.empty_cache()
        except Exception:
            logging.debug("GPU cleanup unavailable", exc_info=True)
        finally:
            with lock:
                active_job = None
                job_progress.pop(job_id, None)


@app.post("/api/generate", status_code=202)
async def create_job(
    image: UploadFile = File(...),
    mode: Literal["real", "synthetic"] = Form("real"),
    steps: int = Form(50, ge=10, le=100),
    seed: int = Form(42, ge=0, le=2**31 - 1),
    num_gaussians: int = Form(262144),
    cfg_strength: float = Form(3.0, ge=0, le=10),
    rescale_t: float = Form(3.0, ge=1, le=6),
):
    global active_job
    if num_gaussians not in (65536, 131072, 262144, 524288, 1048576):
        raise HTTPException(422, "Choose a supported Gaussian count.")
    if not status()["ready"]:
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
    job_id = uuid4().hex
    folder = OUTPUTS / job_id
    with lock:
        if active_job:
            raise HTTPException(409, "A generation is already running. Wait for it to finish.")
        folder.mkdir()
        prepared.save(folder / "input.png")
        jobs[job_id] = {"id": job_id, "state": "running", "stage": "starting", "eta_seconds": None,
                        "started_at": time.time(), "message": "Starting…", "settings": settings}
        active_job = job_id
        try:
            executor.submit(generate, job_id, folder / "input.png", settings)
        except Exception:
            active_job = None
            jobs.pop(job_id, None)
            raise
    return {"id": job_id}


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


app.mount("/outputs", StaticFiles(directory=OUTPUTS), name="outputs")
if (ROOT / "dist").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="web")
