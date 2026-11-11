import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gpu_reservation import Reservation, ReservationBusy, application_reservation, inherited_fds


def wait_file(path):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if path.exists():return
        time.sleep(.01)
    raise AssertionError('Disposable worker did not become ready.')


CHILD="""import os,sys,time
from pathlib import Path
fd=int(sys.argv[1]);os.fstat(fd)
assert os.get_inheritable(fd)
Path(sys.argv[2]).write_text('ready')
end=time.monotonic()+15
while not Path(sys.argv[3]).exists() and time.monotonic()<end:time.sleep(.01)
"""


def test_private_reservation_excludes_a_second_owner_and_can_be_reused(tmp_path):
    path=tmp_path/'gpu.lock'
    with Reservation(path):
        assert stat.S_IMODE(path.stat().st_mode)==0o600 and path.stat().st_size==0
        with pytest.raises(ReservationBusy):Reservation(path).acquire()
    with Reservation(path):pass
    assert path.exists()


def test_default_resource_is_shared_across_worktrees(tmp_path,monkeypatch):
    from gpu_reservation import default_resource
    monkeypatch.delenv('IDOL_GPU_RESOURCE',raising=False)
    monkeypatch.setenv('XDG_CACHE_HOME',str(tmp_path/'cache'))
    first=tmp_path/'one';second=tmp_path/'two';first.mkdir();second.mkdir()
    monkeypatch.chdir(first);a=default_resource()
    monkeypatch.chdir(second);b=default_resource()
    assert a==b==tmp_path/'cache/idol-playground/cuda.lock'
    assert not a.exists()


def test_changed_lock_identity_blocks_new_worker_inheritance(tmp_path):
    path=tmp_path/'gpu.lock'
    with application_reservation(path):
        path.rename(tmp_path/'preserved-original')
        path.write_bytes(b'');path.chmod(0o600)
        with pytest.raises(RuntimeError,match='identity'):inherited_fds()
    assert (tmp_path/'preserved-original').exists() and path.exists()


@pytest.mark.parametrize('kind',['symlink','fifo','nonempty','public'])
def test_unsafe_lock_is_refused_without_replacing_it(tmp_path,kind):
    path=tmp_path/'gpu.lock'
    if kind=='symlink':
        target=tmp_path/'owner-data';target.write_text('preserve');path.symlink_to(target)
    elif kind=='fifo':os.mkfifo(path)
    else:
        path.write_bytes(b'owner data' if kind=='nonempty' else b'');path.chmod(0o644 if kind=='public' else 0o600)
    before=path.lstat()
    with pytest.raises((ValueError,OSError)):Reservation(path).acquire()
    assert (path.lstat().st_dev,path.lstat().st_ino)==(before.st_dev,before.st_ino)
    if kind=='symlink':assert target.read_text()=='preserve'


def test_worker_bridge_retains_application_reservation_after_parent_close(tmp_path):
    from worker_leases import WorkerLease
    path=tmp_path/'gpu.lock';ready=tmp_path/'ready';stop=tmp_path/'stop'
    manager=WorkerLease(tmp_path/'lease.json',tmp_path/'worker.lock')
    try:
        with application_reservation(path):
            fd=inherited_fds()[0]
            manager.start([sys.executable,'-c',CHILD,str(fd),str(ready),str(stop)])
            wait_file(ready)
        assert inherited_fds()==()
        with pytest.raises(ReservationBusy):Reservation(path).acquire()
        stop.touch();assert manager.wait(timeout=5)['state']=='exited'
        with Reservation(path):pass
    finally:
        stop.touch()
        if manager.process is not None and manager.process.poll() is None:manager.cancel()


def test_legacy_bridge_passes_reservation_and_cancel_reaps_worker(tmp_path):
    from mesh_runtime import MeshCancelled, run_worker
    path=tmp_path/'gpu.lock';ready=tmp_path/'ready';stop=tmp_path/'stop';cancel=threading.Event();errors=[]
    def launch(fd):
        try:run_worker([sys.executable,'-c',CHILD,str(fd),str(ready),str(stop)],tmp_path,lambda event:None,cancel)
        except BaseException as error:errors.append(error)
    with application_reservation(path):
        thread=threading.Thread(target=launch,args=(inherited_fds()[0],))
        thread.start()
        try:
            wait_file(ready);cancel.set();thread.join(timeout=5)
            assert not thread.is_alive() and len(errors)==1 and isinstance(errors[0],MeshCancelled)
            with pytest.raises(ReservationBusy):Reservation(path).acquire()
        finally:stop.touch();cancel.set();thread.join(timeout=5)
    with Reservation(path):pass


def test_parent_crash_does_not_unlock_a_live_legacy_child(tmp_path):
    path=tmp_path/'gpu.lock';ready=tmp_path/'ready';stop=tmp_path/'stop'
    parent_code="""import sys,threading
from pathlib import Path
from gpu_reservation import application_reservation,inherited_fds
from mesh_runtime import run_worker
with application_reservation(sys.argv[1]):
 run_worker([sys.executable,'-c',sys.argv[4],str(inherited_fds()[0]),sys.argv[2],sys.argv[3]],Path(sys.argv[1]).parent,lambda event:None,threading.Event())
"""
    parent=subprocess.Popen([sys.executable,'-c',parent_code,str(path),str(ready),str(stop),CHILD],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        wait_file(ready);parent.kill();parent.wait(timeout=5)
        with pytest.raises(ReservationBusy):Reservation(path).acquire()
        stop.touch()
        deadline=time.monotonic()+5
        while True:
            try:
                with Reservation(path):break
            except ReservationBusy:
                if time.monotonic()>deadline:raise
                time.sleep(.01)
    finally:
        stop.touch()
        if parent.poll() is None:parent.kill();parent.wait(timeout=5)


def fresh_app(monkeypatch):
    name='reservation_app_'+uuid4().hex
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'app.py')
    module=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,name,module);spec.loader.exec_module(module)
    return module


def test_app_reserves_before_service_start_and_releases_after_shutdown(tmp_path,monkeypatch):
    path=tmp_path/'gpu.lock';monkeypatch.setenv('IDOL_GPU_RESERVATION','1');monkeypatch.setenv('IDOL_GPU_RESOURCE',str(path));monkeypatch.setenv('IDOL_CHARACTERS','0')
    server=fresh_app(monkeypatch)
    with TestClient(server.app) as client:
        assert client.get('/api/status').json()['gpu_reservation']=={'enabled':True,'held':True}
        with pytest.raises(ReservationBusy):Reservation(path).acquire()
    with Reservation(path):pass
    assert inherited_fds()==()


def test_app_shutdown_stops_registered_worker_before_releasing_reservation(tmp_path,monkeypatch):
    from mesh_runtime import MeshCancelled,run_worker
    path=tmp_path/'gpu.lock';ready=tmp_path/'ready';stop=tmp_path/'stop';cancel=threading.Event()
    monkeypatch.setenv('IDOL_GPU_RESERVATION','1');monkeypatch.setenv('IDOL_GPU_RESOURCE',str(path));monkeypatch.setenv('IDOL_CHARACTERS','0')
    server=fresh_app(monkeypatch)
    with TestClient(server.app):
        server.mesh_cancellations['disposable']=cancel
        fd=inherited_fds()[0]
        future=server.executor.submit(run_worker,[sys.executable,'-c',CHILD,str(fd),str(ready),str(stop)],tmp_path,lambda event:None,cancel)
        wait_file(ready)
    assert future.done() and isinstance(future.exception(),MeshCancelled)
    with Reservation(path):pass
    assert inherited_fds()==()


def test_shutdown_unloads_cached_tensors_while_reservation_is_still_held(tmp_path,monkeypatch):
    path=tmp_path/'gpu.lock'
    monkeypatch.setenv('IDOL_GPU_RESERVATION','1');monkeypatch.setenv('IDOL_GPU_RESOURCE',str(path));monkeypatch.setenv('IDOL_CHARACTERS','0')
    server=fresh_app(monkeypatch);observed=[]
    def unload():
        with pytest.raises(ReservationBusy):Reservation(path).acquire()
        observed.append('cache unloaded while reserved')
    monkeypatch.setattr(server,'release_idol',unload)
    with TestClient(server.app):pass
    assert observed==['cache unloaded while reserved']
    with Reservation(path):pass


def test_conflicting_app_does_not_begin_character_store_recovery(tmp_path,monkeypatch):
    path=tmp_path/'gpu.lock';monkeypatch.setenv('IDOL_GPU_RESERVATION','1');monkeypatch.setenv('IDOL_GPU_RESOURCE',str(path));monkeypatch.setenv('IDOL_CHARACTERS','1')
    import character_service
    recovered=[]
    monkeypatch.setattr(character_service,'CharacterService',lambda *args:recovered.append(True))
    server=fresh_app(monkeypatch)
    try:
        with Reservation(path),pytest.raises(ReservationBusy):
            with TestClient(server.app):pass
        assert recovered==[]
    finally:server.executor.shutdown(wait=True)


def test_startup_error_does_not_leak_reservation(tmp_path,monkeypatch):
    path=tmp_path/'gpu.lock';monkeypatch.setenv('IDOL_GPU_RESERVATION','1');monkeypatch.setenv('IDOL_GPU_RESOURCE',str(path));monkeypatch.setenv('IDOL_CHARACTERS','1')
    import character_service
    def fail(*args):raise RuntimeError('Disposable startup failure')
    monkeypatch.setattr(character_service,'CharacterService',fail);server=fresh_app(monkeypatch)
    try:
        with pytest.raises(RuntimeError,match='Disposable startup failure'):
            with TestClient(server.app):pass
        with Reservation(path):pass
        assert inherited_fds()==()
    finally:server.executor.shutdown(wait=True)


def test_application_and_stage_resource_collision_is_rejected_before_recovery(tmp_path,monkeypatch):
    path=tmp_path/'gpu.lock'
    monkeypatch.setenv('IDOL_GPU_RESERVATION','1');monkeypatch.setenv('IDOL_GPU_RESOURCE',str(path))
    monkeypatch.setenv('IDOL_CHARACTERS','1');monkeypatch.setenv('IDOL_CHARACTER_RESOURCE',str(path))
    server=fresh_app(monkeypatch)
    try:
        with pytest.raises(ValueError,match='distinct'):
            with TestClient(server.app):pass
        with Reservation(path):pass
    finally:server.executor.shutdown(wait=True)


def test_disabled_app_does_not_touch_configured_resource(tmp_path,monkeypatch):
    path=tmp_path/'unused.lock';monkeypatch.setenv('IDOL_GPU_RESERVATION','0');monkeypatch.setenv('IDOL_GPU_RESOURCE',str(path));monkeypatch.setenv('IDOL_CHARACTERS','0');server=fresh_app(monkeypatch)
    with TestClient(server.app) as client:
        assert client.get('/api/status').json()['gpu_reservation']=={'enabled':False,'held':False}
    assert not path.exists()


def test_relative_configuration_and_unsupported_platform_are_refused(tmp_path,monkeypatch):
    with pytest.raises(ValueError):Reservation(Path('relative.lock')).acquire()
    import gpu_reservation
    monkeypatch.setattr(gpu_reservation.sys,'platform','darwin')
    with pytest.raises(RuntimeError,match='Linux'):Reservation(tmp_path/'gpu.lock').acquire()
    assert not (tmp_path/'gpu.lock').exists()
