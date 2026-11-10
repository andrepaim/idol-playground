from io import BytesIO
from contextlib import nullcontext
import time
import types

from fastapi.testclient import TestClient
from PIL import Image
import pytest

import app as server


def image_bytes():
    stream = BytesIO()
    Image.new("RGB", (40, 30), "orange").save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "OUTPUTS", tmp_path)
    monkeypatch.setattr(server, "status", lambda: {"ready": True})
    monkeypatch.setattr(server, "active_job", None)
    monkeypatch.setattr(server, "jobs", {})
    monkeypatch.setattr(server, "job_progress", {})
    monkeypatch.setattr(server, "instrument_pipeline", lambda *args: nullcontext())
    return TestClient(server.app)


def submit(client, **data):
    return client.post("/api/generate", files={"image": ("photo.png", image_bytes(), "image/png")}, data=data)


def wait_for_job(client, job_id):
    for _ in range(100):
        result = client.get(f"/api/jobs/{job_id}").json()
        if result["state"] != "running" and server.active_job is None:
            return result
        time.sleep(0.01)
    pytest.fail("Job did not finish")


def test_rejects_file_disguised_as_image(client):
    response = client.post("/api/generate", files={"image": ("image.png", b"not an image", "image/png")})
    assert response.status_code == 422
    assert server.active_job is None


def test_enforces_upload_limit(client, monkeypatch):
    monkeypatch.setattr(server, "MAX_UPLOAD", 20)
    assert submit(client).status_code == 413


def test_rejects_unsupported_image_format(client):
    stream = BytesIO()
    Image.new("RGB", (40, 30)).save(stream, format="GIF")
    response = client.post("/api/generate", files={"image": ("image.png", stream.getvalue(), "image/png")})
    assert response.status_code == 422


@pytest.mark.parametrize("settings", [{"steps": 0}, {"num_gaussians": 17}, {"mode": "unknown"}, {"seed": -1}])
def test_invalid_settings_rejected(client, settings):
    assert submit(client, **settings).status_code == 422


def test_concurrent_generation_rejected(client, monkeypatch):
    monkeypatch.setattr(server, "active_job", "existing")
    assert submit(client).status_code == 409


def test_missing_setup_is_actionable(client, monkeypatch):
    monkeypatch.setattr(server, "status", lambda: {"ready": False})
    response = submit(client)
    assert response.status_code == 503
    assert "uv sync --extra local" in response.json()["detail"]


def test_generation_saves_downloadable_artifacts(client, monkeypatch):
    import sys

    class Gaussian:
        def save_ply(self, path):
            from pathlib import Path
            Path(path).write_bytes(b"ply\nformat ascii 1.0\nend_header\n")

    def model(image, **settings):
        assert settings["seed"] == 123
        return types.SimpleNamespace(gaussian=Gaussian(), preprocessed_image=Image.open(image), camera={"yaw": 0})

    monkeypatch.setattr(server, "pipeline", model)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: True, empty_cache=lambda: None, synchronize=lambda: None)))
    monkeypatch.setitem(sys.modules, "idol", types.SimpleNamespace(IdolPipeline=object))
    result = submit(client, seed=123)
    assert result.status_code == 202
    job = wait_for_job(client, result.json()["id"])
    assert job["state"] == "complete", job
    assert set(job["files"]) == {"object.ply", "prepared.png", "settings.json", "camera.json"}
    # The test substitutes storage and mounts that directory for download verification.
    from fastapi.staticfiles import StaticFiles
    from starlette.routing import Mount
    mount = next(route for route in server.app.routes if isinstance(route, Mount) and route.path == "/outputs")
    monkeypatch.setattr(mount, "app", StaticFiles(directory=server.OUTPUTS))
    response = client.get(job["files"]["object.ply"])
    assert response.status_code == 200
    assert response.content.startswith(b"ply\n")
    assert client.get(job["files"]["settings.json"]).json()["seed"] == 123
    server.jobs.clear()
    assert client.get(f'/api/jobs/{job["id"]}').json()["state"] == "complete"


def test_model_error_releases_gpu_slot(client, monkeypatch):
    import sys

    def fail(*args, **kwargs):
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(server, "pipeline", fail)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: True, empty_cache=lambda: None, synchronize=lambda: None)))
    monkeypatch.setitem(sys.modules, "idol", types.SimpleNamespace(IdolPipeline=object))
    response = submit(client)
    job = wait_for_job(client, response.json()["id"])
    assert job["state"] == "error"
    assert "Lower" in job["message"] or "lower" in job["message"]
    for _ in range(100):
        if server.active_job is None:
            break
        time.sleep(0.01)
    assert server.active_job is None


def fake_torch(cuda, mps, calls):
    def accelerator(name, available):
        return types.SimpleNamespace(is_available=lambda: available, empty_cache=lambda: calls.append(f"{name} release"),
                                     synchronize=lambda: calls.append(f"{name} sync"))
    return types.SimpleNamespace(cuda=accelerator("cuda", cuda), mps=accelerator("mps", mps),
                                 backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: mps)))


def test_generation_uses_apple_silicon_gpu_without_cuda(client, monkeypatch):
    import sys

    calls, loaded = [], {}

    class Gaussian:
        def save_ply(self, path):
            from pathlib import Path
            Path(path).write_bytes(b"ply\nformat ascii 1.0\nend_header\n")

    class IdolPipeline:
        @classmethod
        def from_pretrained(cls, weights, device, **kwargs):
            loaded["device"] = device
            return lambda image, **settings: types.SimpleNamespace(
                gaussian=Gaussian(), preprocessed_image=Image.open(image), camera={"yaw": 0})

    def instrument(pipeline, progress, synchronize):
        synchronize()
        return nullcontext()

    monkeypatch.setattr(server, "pipeline", None)
    monkeypatch.setattr(server, "models_ready", lambda: True)
    monkeypatch.setattr(server, "ensure_models", lambda: ("weights", {}))
    monkeypatch.setattr(server, "instrument_pipeline", instrument)
    monkeypatch.setitem(sys.modules, "torch", fake_torch(cuda=False, mps=True, calls=calls))
    monkeypatch.setitem(sys.modules, "idol", types.SimpleNamespace(IdolPipeline=IdolPipeline))
    job = wait_for_job(client, submit(client).json()["id"])
    assert job["state"] == "complete", job
    assert loaded["device"] == "mps"
    assert calls == ["mps sync", "mps release"]


def test_generation_without_any_gpu_is_actionable(client, monkeypatch):
    import sys

    monkeypatch.setattr(server, "pipeline", None)
    monkeypatch.setitem(sys.modules, "torch", fake_torch(cuda=False, mps=False, calls=[]))
    monkeypatch.setitem(sys.modules, "idol", types.SimpleNamespace(IdolPipeline=object))
    job = wait_for_job(client, submit(client).json()["id"])
    assert job["state"] == "error"
    assert "Apple Silicon" in job["message"]


def test_unknown_job_returns_404(client):
    assert client.get("/api/jobs/missing").status_code == 404


def test_public_model_setup_does_not_require_hugging_face_login(monkeypatch):
    monkeypatch.setattr(server, "find_spec", lambda name: object())
    monkeypatch.setattr(server, "models_ready", lambda: True)
    client = TestClient(server.app)
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["weights_downloaded"] is True
