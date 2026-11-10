import pytest


def test_four_beat_support_and_periodic_foot_velocity():
    from walk_motion import foot_path, CENTERS, DUTY

    # All four landings must be distinct and alternate lateral hind/fore pairs.
    assert [(n, round((c - DUTY / 2) % 1, 4)) for n, c in CENTERS.items()] == [
        ("hind_left", 0.0),
        ("fore_left", 0.25),
        ("hind_right", 0.5),
        ("fore_right", 0.75),
    ]
    for i in range(201):
        phase = i / 200
        feet = [foot_path(phase, c, 0.18, 0.05) for c in CENTERS.values()]
        assert sum(p[2] for p in feet) >= 2
        for c in CENTERS.values():
            assert foot_path(phase, c, 0.18, 0.05)[:2] == pytest.approx(foot_path(phase + 1, c, 0.18, 0.05)[:2])
            x, z, stance = foot_path(phase, c, 0.18, 0.05)
            if stance and abs(z) < 1e-9:
                eps = 1e-6
                dx = (foot_path(phase + eps, c, 0.18, 0.05)[0] - foot_path(phase - eps, c, 0.18, 0.05)[0]) / (2 * eps)
                assert dx + 0.18 == pytest.approx(0, abs=1e-4)  # world stance cancels root travel
    for c in CENTERS.values():
        for edge in (c - DUTY / 2, c + DUTY / 2):
            e = 1e-5
            a = foot_path(edge - e, c, 0.18, 0.05)
            b = foot_path(edge, c, 0.18, 0.05)
            d = foot_path(edge + e, c, 0.18, 0.05)
            assert [(b[k] - a[k]) / e for k in (0, 1)] == pytest.approx([(d[k] - b[k]) / e for k in (0, 1)], abs=0.001)


def test_profile_refuses_wrong_topology_or_unreviewed_role_assignments():
    from walk_motion import profile_from_glb, validate_roles, PARENTS, PAWS
    import json, struct

    def fixture(parents):
        nodes = [
            {"name": f"bone_{i}", "children": [j for j, p in enumerate(parents) if p == i]} for i in range(len(parents))
        ]
        doc = json.dumps({"nodes": nodes, "skins": [{"joints": list(range(len(parents)))}]}).encode()
        return b"glTF" + struct.pack("<II", 2, 20 + len(doc)) + struct.pack("<I", len(doc)) + b"JSON" + doc

    assert profile_from_glb(fixture(PARENTS))["supported"]
    altered = list(PARENTS)
    altered[22] = 2
    assert not profile_from_glb(fixture(altered))["supported"]
    assert not profile_from_glb(b"bad")["supported"]
    assert validate_roles(PAWS, True) == PAWS
    with pytest.raises(ValueError, match="[Rr]eview"):
        validate_roles(PAWS, False)
    bad = {**PAWS, "fore_left": "bone_33"}
    with pytest.raises(ValueError):
        validate_roles(bad, True)
    # Only symmetric left/right reassignment within matching limb chains is supported.
    assert validate_roles({**PAWS, "fore_left": "bone_19", "fore_right": "bone_14"}, True)


def test_walk_api_source_review_setup_busy_preservation_and_reopening(monkeypatch, tmp_path):
    import app as server
    import time, json
    from fastapi.testclient import TestClient
    from walk_motion import PAWS, PROFILE

    source = "a" * 32
    folder = tmp_path / source
    folder.mkdir()
    (folder / "rigged.glb").write_bytes(b"original")
    (folder / "skin.fbx").write_bytes(b"skin")
    original = {"id": source, "state": "complete", "output_type": "rig"}
    monkeypatch.setattr(server, "OUTPUTS", tmp_path)
    monkeypatch.setattr(server, "jobs", {source: original.copy()})
    monkeypatch.setattr(server, "active_job", None)
    monkeypatch.setattr(server, "mesh_cancellations", {})
    monkeypatch.setattr(server, "job_progress", {})
    monkeypatch.setattr(server, "walk_backend_installed", lambda: False, raising=False)
    monkeypatch.setattr(
        server, "profile_from_glb", lambda data: {"supported": True, "profile": PROFILE, "paws": PAWS}, raising=False
    )
    client = TestClient(server.app)
    body = {"profile": PROFILE, "paws": json.dumps(PAWS), "reviewed": "true"}
    assert client.post("/api/jobs/missing/walk", data=body).status_code == 404
    assert client.post(f"/api/jobs/{source}/walk", data=body).status_code == 503
    monkeypatch.setattr(server, "walk_backend_installed", lambda: True)
    assert client.post(f"/api/jobs/{source}/walk", data={**body, "reviewed": "false"}).status_code == 422
    assert client.post(f"/api/jobs/{source}/walk", data={**body, "paws": "[]"}).status_code == 422
    monkeypatch.setattr(server, "active_job", "occupied")
    assert client.post(f"/api/jobs/{source}/walk", data=body).status_code == 409
    monkeypatch.setattr(server, "active_job", None)
    calls = []
    monkeypatch.setattr(server, "release_idol", lambda: calls.append("release"))

    def worker(src, dst, settings, emit, cancel):
        assert calls == ["release"]
        assert src == folder
        assert settings["paws"] == PAWS
        emit({"stage": "walk_bake", "message": "Contact frame", "step": 1, "total_steps": 49})
        for name in (
            "animated.glb",
            "walk-inplace.glb",
            "walk-forward.glb",
            "animated.fbx",
            "character.blend",
            "walk.json",
        ):
            (dst / name).write_bytes(b"fixture")
        return {"bones": 38, "triangles": 1, "warnings": ["Experimental"]}

    monkeypatch.setattr(server, "generate_walk", worker, raising=False)
    response = client.post(f"/api/jobs/{source}/walk", data=body)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    for _ in range(100):
        job = client.get("/api/jobs/" + job_id).json()
        if job["state"] != "running" and server.active_job is None:
            break
        time.sleep(0.01)
    assert job["state"] == "complete", job
    assert job["output_type"] == "walk" and job["source_job"] == source
    assert job["walk"]["bones"] == 38 and "walk-forward.glb" in job["files"]
    assert server.jobs[source] == original and (folder / "rigged.glb").read_bytes() == b"original"
    server.jobs.pop(job_id)
    assert client.get("/api/jobs/" + job_id).json()["output_type"] == "walk"
    assert any(j["id"] == job_id and j["output_type"] == "walk" for j in client.get("/api/jobs").json()["jobs"])
    (folder / "skin.fbx").unlink()
    assert client.get(f"/api/jobs/{source}/walk-profile").status_code == 409


def test_walk_cancel_reaps_before_slot_release(monkeypatch, tmp_path):
    import app as server
    import threading, time, json
    from mesh_runtime import MeshCancelled
    from fastapi.testclient import TestClient
    from walk_motion import PAWS, PROFILE

    source = "c" * 32
    folder = tmp_path / source
    folder.mkdir()
    (folder / "rigged.glb").write_bytes(b"rig")
    (folder / "skin.fbx").write_bytes(b"skin")
    monkeypatch.setattr(server, "OUTPUTS", tmp_path)
    monkeypatch.setattr(server, "jobs", {source: {"id": source, "state": "complete", "output_type": "rig"}})
    monkeypatch.setattr(server, "active_job", None)
    monkeypatch.setattr(server, "mesh_cancellations", {})
    monkeypatch.setattr(server, "job_progress", {})
    monkeypatch.setattr(server, "release_idol", lambda: None)
    monkeypatch.setattr(server, "walk_backend_installed", lambda: True, raising=False)
    monkeypatch.setattr(server, "profile_from_glb", lambda data: {"supported": True}, raising=False)
    stopped = threading.Event()
    allow_reap = threading.Event()

    def worker(src, dst, settings, emit, cancel):
        assert cancel.wait(5)
        stopped.set()
        assert allow_reap.wait(5)
        raise MeshCancelled("cancelled")

    monkeypatch.setattr(server, "generate_walk", worker, raising=False)
    client = TestClient(server.app)
    body = {"profile": PROFILE, "paws": json.dumps(PAWS), "reviewed": "true"}
    response = client.post(f"/api/jobs/{source}/walk", data=body)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 202
    assert stopped.wait(2)
    assert server.active_job == job_id
    assert client.post(f"/api/jobs/{source}/walk", data=body).status_code == 409
    allow_reap.set()
    for _ in range(100):
        if server.active_job is None:
            break
        time.sleep(0.01)
    assert client.get(f"/api/jobs/{job_id}").json()["state"] == "cancelled"
    assert json.loads((tmp_path / job_id / "job.json").read_text())["state"] == "cancelled"
