"""Own disposable subprocesses only. Never signals app/user/other-session jobs."""
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from worker_leases import WorkerLease, ResourceBusy, OwnershipError

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux/WSL worker lease protocol')


def wait_file(path, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists():
            return
        time.sleep(.02)
    pytest.fail('Owned worker did not become ready')


def sleeper(ready):
    return [sys.executable, '-c', "from pathlib import Path;import sys,time;Path(sys.argv[1]).write_text('ready');time.sleep(600)", str(ready)]


def test_launch_exit_and_private_durable_lease(tmp_path):
    manager = WorkerLease(tmp_path/'one.json', tmp_path/'resource.lock')
    process = manager.start([sys.executable, '-c', "print('owned fixture')"])
    result = manager.wait(timeout=5)
    assert result['returncode'] == 0
    assert process.returncode == 0
    record = json.loads((tmp_path/'one.json').read_text())
    assert record['state'] == 'exited'
    assert record['worker']['pid'] == process.pid
    assert len(record['nonce']) == 32
    assert (tmp_path/'one.json').stat().st_mode & 0o777 == 0o600
    assert (tmp_path/'one.stdout.log').stat().st_mode & 0o777 == 0o600
    assert (tmp_path/'one.stderr.log').stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        manager.start([sys.executable, '-c', 'pass'])


def test_live_resource_blocks_second_worker_until_cancelled_and_reaped(tmp_path):
    first = WorkerLease(tmp_path/'first.json', tmp_path/'resource.lock')
    second = WorkerLease(tmp_path/'second.json', tmp_path/'resource.lock')
    ready = tmp_path/'ready'
    first.start(sleeper(ready))
    try:
        wait_file(ready)
        with pytest.raises(ResourceBusy):
            second.start([sys.executable, '-c', 'pass'])
        with pytest.raises(subprocess.TimeoutExpired):
            first.wait(timeout=.05)
        with pytest.raises(ResourceBusy):
            second.start([sys.executable, '-c', 'pass'])
        result = first.cancel(grace=.2)
        assert result['state'] == 'cancelled'
        assert first.process.poll() is not None
        second.start([sys.executable, '-c', 'pass'])
        assert second.wait(timeout=5)['returncode'] == 0
    finally:
        if first.process.poll() is None:
            first.cancel()
        if second.process is not None and second.process.poll() is None:
            second.cancel()


def test_persistence_failure_never_grants_command_execution(tmp_path, monkeypatch):
    manager = WorkerLease(tmp_path/'failed.json', tmp_path/'resource.lock')
    ready = tmp_path/'must-not-run'
    monkeypatch.setattr(manager, '_persist', lambda _: (_ for _ in ()).throw(OSError('Injected persistence failure')))
    with pytest.raises(OSError):
        manager.start(sleeper(ready))
    assert not ready.exists()
    assert manager.process.poll() is not None
    other = WorkerLease(tmp_path/'retry.json', tmp_path/'resource.lock')
    other.start([sys.executable, '-c', 'pass'])
    assert other.wait(timeout=5)['returncode'] == 0


def test_parent_must_not_recover_a_live_owners_worker(tmp_path):
    first = WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock')
    first.start(sleeper(tmp_path/'ready'))
    try:
        with pytest.raises(OwnershipError):
            WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock').recover(grace=.2)
        assert first.process.poll() is None
    finally:
        first.cancel()


def test_parent_death_stops_worker_and_can_be_reconciled(tmp_path):
    lease, resource, ready = tmp_path/'lease.json', tmp_path/'resource.lock', tmp_path/'ready'
    code = """import sys,time
from worker_leases import WorkerLease
m=WorkerLease(sys.argv[1],sys.argv[2]);m.start([sys.executable,'-c',"from pathlib import Path;import sys,time;Path(sys.argv[1]).write_text('ready');time.sleep(600)",sys.argv[3]])
time.sleep(600)
"""
    parent = subprocess.Popen([sys.executable, '-c', code, str(lease), str(resource), str(ready)], cwd=Path(__file__).parents[1])
    try:
        wait_file(ready)
        parent.kill()
        parent.wait(timeout=5)
        recovered = WorkerLease(lease, resource).recover(grace=.3)
        assert recovered['state'] == 'interrupted'
        replacement = WorkerLease(tmp_path/'replacement.json', resource)
        replacement.start([sys.executable, '-c', 'pass'])
        assert replacement.wait(timeout=5)['returncode'] == 0
    finally:
        if parent.poll() is None:
            parent.terminate()
            parent.wait(timeout=5)


def test_foreign_identity_and_bad_lease_never_signal_process(tmp_path):
    manager = WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock')
    manager.start(sleeper(tmp_path/'ready'))
    original = json.loads((tmp_path/'lease.json').read_text())
    foreign = subprocess.Popen(sleeper(tmp_path/'foreign-ready'))
    try:
        wait_file(tmp_path/'foreign-ready')
        payload = {**original, 'nonce':'0'*32}
        (tmp_path/'lease.json').write_text(json.dumps(payload))
        with pytest.raises(OwnershipError):
            manager.cancel(grace=.1)
        assert foreign.poll() is None
        assert manager.process.poll() is None
        (tmp_path/'lease.json').write_text('{broken')
        with pytest.raises(ValueError):
            WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock').recover()
        assert foreign.poll() is None
    finally:
        (tmp_path/'lease.json').write_text(json.dumps(original))
        manager.cancel(grace=.2)
        foreign.terminate()
        foreign.wait(timeout=5)


def test_python_startup_hooks_cannot_execute_before_lease_grant(tmp_path, monkeypatch):
    import os
    hooks = tmp_path/'hooks'
    hooks.mkdir()
    marker = tmp_path/'startup-must-not-run'
    (hooks/'sitecustomize.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("ran")\n')
    manager = WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock')
    monkeypatch.setattr(manager, '_persist', lambda _: (_ for _ in ()).throw(OSError('Injected persistence failure')))
    with pytest.raises(OSError):
        manager.start([sys.executable, '-c', 'pass'], env={**os.environ, 'PYTHONPATH':str(hooks)})
    assert not marker.exists()


def test_invalid_grace_cannot_signal_a_live_worker(tmp_path):
    manager = WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock')
    manager.start(sleeper(tmp_path/'ready'))
    try:
        wait_file(tmp_path/'ready')
        for grace in [-1, float('nan'), float('inf')]:
            with pytest.raises(ValueError):
                manager.cancel(grace=grace)
            assert manager.process.poll() is None
    finally:
        manager.cancel()


def test_recovery_refuses_foreign_or_reused_worker_identity(tmp_path):
    from worker_leases import _identity
    manager = WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock')
    manager.start([sys.executable, '-c', 'pass'])
    record = manager.wait(timeout=5)
    foreign = subprocess.Popen(sleeper(tmp_path/'foreign-ready'))
    try:
        wait_file(tmp_path/'foreign-ready')
        record['parent'] = record['worker']  # known exited fixture, not this live test runner
        record['worker'] = _identity(foreign.pid)
        for reused in (False, True):
            payload = json.loads(json.dumps(record))
            if reused:
                payload['worker']['start_ticks'] += 1
            (tmp_path/'lease.json').write_text(json.dumps(payload))
            with pytest.raises(OwnershipError):
                WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock').recover(grace=.1)
            assert foreign.poll() is None
    finally:
        foreign.terminate()
        foreign.wait(timeout=5)


def test_cooperating_descendant_retains_resource_and_is_stopped(tmp_path):
    ready = tmp_path/'descendant-ready'
    code = '''import os,subprocess,sys
child=subprocess.Popen([sys.executable,'-c',"from pathlib import Path;import sys,time;Path(sys.argv[1]).write_text('ready');time.sleep(600)",sys.argv[1]],pass_fds=(int(os.environ['IDOL_RESOURCE_FD']),))
child.wait()
'''
    manager = WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock')
    manager.start([sys.executable, '-c', code, str(ready)])
    try:
        wait_file(ready)
        record = manager.cancel(grace=.2)
        assert not manager._owned(record)
        replacement = WorkerLease(tmp_path/'replacement.json', tmp_path/'resource.lock')
        replacement.start([sys.executable, '-c', 'pass'])
        assert replacement.wait(timeout=5)['returncode'] == 0
    finally:
        if manager.process.poll() is None:
            manager.cancel()


def test_recovery_cannot_report_completion_while_resource_still_owned(tmp_path):
    import fcntl
    import os
    manager = WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock')
    manager.start([sys.executable, '-c', 'pass'])
    record = manager.wait(timeout=5)
    record['parent'] = record['worker']
    (tmp_path/'lease.json').write_text(json.dumps(record))
    descriptor = os.open(tmp_path/'resource.lock', os.O_RDWR)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(OwnershipError, match='resource'):
            WorkerLease(tmp_path/'lease.json', tmp_path/'resource.lock').recover(grace=0)
        assert json.loads((tmp_path/'lease.json').read_text())['state'] == 'exited'
    finally:
        os.close(descriptor)


def test_pipe_setup_failure_releases_reservation(tmp_path, monkeypatch):
    import worker_leases
    manager = WorkerLease(tmp_path/'failed.json', tmp_path/'resource.lock')
    with monkeypatch.context() as patch:
        patch.setattr(worker_leases.os, 'pipe', lambda: (_ for _ in ()).throw(OSError('Injected descriptor exhaustion')))
        with pytest.raises(OSError):
            manager.start([sys.executable, '-c', 'pass'])
    retry = WorkerLease(tmp_path/'retry.json', tmp_path/'resource.lock')
    retry.start([sys.executable, '-c', 'pass'])
    assert retry.wait(timeout=5)['returncode'] == 0


def test_exiting_worker_without_readable_environment_is_observed_without_signals(tmp_path,monkeypatch):
    import worker_leases
    manager=WorkerLease(tmp_path/'lease.json',tmp_path/'resource.lock')
    ready=tmp_path/'ready';stop=tmp_path/'stop'
    code="""from pathlib import Path
import sys,time
Path(sys.argv[1]).write_text('ready')
while not Path(sys.argv[2]).exists(): time.sleep(.01)
"""
    manager.start([sys.executable,'-c',code,str(ready),str(stop)])
    try:
        wait_file(ready)
        original=worker_leases._markers
        def unreadable_during_exit(pid,record):
            if pid==manager.process.pid:
                stop.write_text('exit normally')
                return False
            return original(pid,record)
        with monkeypatch.context() as patch:
            patch.setattr(worker_leases,'_markers',unreadable_during_exit)
            result=manager.cancel(grace=.3)
        assert result['returncode']==0  # no TERM/KILL sent to an unverifiable process
    finally:
        stop.write_text('exit normally')
        if manager.process.poll() is None:
            manager.wait(timeout=5)
