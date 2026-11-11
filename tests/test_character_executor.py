"""Real owned subprocesses and private temporary stores, never owner jobs."""
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import time

import pytest

from character_contracts import new_character
from character_coordinator import Decision, StageBusy
from character_store import CharacterStore
from character_executor import Adapter, StageExecutor, ServiceBusy

IDENTITY = 'a'*32
ORIGINAL = b'fixture'
INPUT_HASHES = {'upload':sha256(ORIGINAL).hexdigest()}
pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux worker ownership')


def command(context):
    return [sys.executable, '-c', "from pathlib import Path;import sys,time;time.sleep(float(sys.argv[2]));Path(sys.argv[1]).write_bytes(b'fixture')",
            str(context.workspace/'input.png'), str(context.parameters.get('delay',0))]


def accept(paths):
    assert paths['input.png'].read_bytes() == ORIGINAL
    return Decision('accept', {'kind':'disposable fixture'})


def adapter(build=command, validator=accept):
    return Adapter('input', {'adapter':'fixture-v1'}, ('input.png',), build, validator)


@pytest.fixture
def setup(tmp_path):
    store = CharacterStore(tmp_path/'store')
    store.save(new_character(IDENTITY), expected_revision=None)
    return store, tmp_path/'resource.lock'


def start(service, **parameters):
    return service.start(IDENTITY, 'fixture', parameters, {}, external_inputs=INPUT_HASHES)


def test_success_cache_and_exclusive_namespace(setup):
    store, resource = setup
    with StageExecutor(store, resource, {'fixture':adapter()}) as service:
        with pytest.raises(ServiceBusy):
            StageExecutor(store, resource, {'fixture':adapter()})
        claim = start(service)
        result = service.wait(claim, timeout=5)
        assert result['stages']['input']['state'] == 'succeeded'
        before = list((store.root/IDENTITY/'runs'/'input').iterdir())
        cached = start(service)
        assert cached.cached
        assert service.wait(cached)['revision'] == result['revision']
        assert list((store.root/IDENTITY/'runs'/'input').iterdir()) == before
    with StageExecutor(store, resource, {'fixture':adapter()}) as replacement:
        assert start(replacement).cached


def test_timeout_duplicate_and_cancel_retry(setup):
    store, resource = setup
    with StageExecutor(store, resource, {'fixture':adapter()}) as service:
        old = start(service, delay=600)
        with pytest.raises(subprocess.TimeoutExpired):
            service.wait(old, timeout=.05)
        assert store.load(IDENTITY)['stages']['input']['state'] == 'running'
        with pytest.raises(StageBusy):
            start(service)
        ended = service.cancel(old, grace=.1)
        assert ended['stages']['input']['state'] == 'cancelled'
        new = start(service)
        assert new.attempt == 2
        assert service.wait(new, timeout=5)['stages']['input']['state'] == 'succeeded'
        assert len(list((store.root/IDENTITY/'runs'/'input').iterdir())) == 2


def test_worker_failure_and_validation_rejection(setup):
    store, resource = setup
    failing = adapter(lambda _: [sys.executable,'-c','raise SystemExit(17)'])
    rejected = adapter(validator=lambda _: Decision('reject', {'reason':'fixture rejection'}))
    with StageExecutor(store, resource, {'failure':failing,'reject':rejected}) as service:
        claim = service.start(IDENTITY,'failure',{}, {},external_inputs=INPUT_HASHES)
        assert service.wait(claim,timeout=5)['stages']['input']['state']=='failed'
        claim = service.start(IDENTITY,'reject',{}, {},external_inputs=INPUT_HASHES)
        assert service.wait(claim,timeout=5)['stages']['input']['state']=='failed'


def test_close_cancels_before_releasing_service_namespace(setup):
    store, resource = setup
    service = StageExecutor(store, resource, {'fixture':adapter()})
    start(service, delay=600)
    service.close()
    assert store.load(IDENTITY)['stages']['input']['state'] == 'cancelled'
    with StageExecutor(store, resource, {'fixture':adapter()}) as replacement:
        claim=start(replacement)
        assert replacement.wait(claim,timeout=5)['stages']['input']['state']=='succeeded'
    with pytest.raises(RuntimeError):
        start(service)


def test_startup_reconciles_claim_before_worker_launch(setup):
    from character_coordinator import StageCoordinator
    store, resource = setup
    claim = StageCoordinator(store).start(IDENTITY,'input',{}, {'adapter':'fixture-v1'}, {},external_inputs=INPUT_HASHES)
    with StageExecutor(store,resource,{'fixture':adapter()}) as service:
        assert store.load(IDENTITY)['stages']['input']['state']=='interrupted'
        retry=start(service)
        assert retry.attempt==claim.attempt+1
        assert service.wait(retry,timeout=5)['stages']['input']['state']=='succeeded'


def test_unknown_adapter_cannot_claim_or_execute(setup):
    store,resource=setup
    with StageExecutor(store,resource,{'fixture':adapter()}) as service:
        before=store.load(IDENTITY)
        with pytest.raises(ValueError):
            service.start(IDENTITY,'unregistered',{}, {},external_inputs=INPUT_HASHES)
        assert store.load(IDENTITY)==before


def test_server_crash_recovery_and_retry(setup):
    store,resource=setup
    ready=store.root.parent/'ready'
    code='''import sys,time
from pathlib import Path
from character_store import CharacterStore
from character_executor import StageExecutor,Adapter
from character_coordinator import Decision
from hashlib import sha256
def command(ctx):
 return [sys.executable,'-c',"from pathlib import Path;import sys,time;Path(sys.argv[1]).write_text('ready');time.sleep(600)",sys.argv[3]]
service=StageExecutor(CharacterStore(sys.argv[1]),sys.argv[2],{'fixture':Adapter('input',{'adapter':'fixture-v1'},('input.png',),command,lambda _:Decision('accept',{}))})
service.start('a'*32,'fixture',{}, {},external_inputs={'upload':sha256(b'fixture').hexdigest()})
time.sleep(600)
'''
    parent=subprocess.Popen([sys.executable,'-c',code,str(store.root),str(resource),str(ready)],cwd=Path(__file__).parents[1])
    try:
        until=time.monotonic()+5
        while not ready.exists() and time.monotonic()<until: time.sleep(.02)
        assert ready.exists()
        parent.kill();parent.wait(timeout=5)
        with StageExecutor(store,resource,{'fixture':adapter()}) as service:
            assert store.load(IDENTITY)['stages']['input']['state']=='interrupted'
            claim=start(service)
            assert service.wait(claim,timeout=5)['stages']['input']['state']=='succeeded'
    finally:
        if parent.poll() is None: parent.terminate();parent.wait(timeout=5)


def test_launch_and_snapshot_errors_never_accept_stage(setup):
    from character_coordinator import StageValidationError
    store,resource=setup
    def bad_command(_):
        raise ValueError('Injected adapter configuration failure')
    with StageExecutor(store,resource,{'broken':adapter(bad_command),'invalid':adapter(validator=lambda _:True),'fixture':adapter()}) as service:
        with pytest.raises(ValueError):
            service.start(IDENTITY,'broken',{}, {},external_inputs=INPUT_HASHES)
        assert store.load(IDENTITY)['stages']['input']['state']=='failed'
        claim=service.start(IDENTITY,'invalid',{}, {},external_inputs=INPUT_HASHES)
        with pytest.raises(StageValidationError):
            service.wait(claim,timeout=5)
        assert store.load(IDENTITY)['stages']['input']['state']=='failed'
        claim=start(service)
        assert service.wait(claim,timeout=5)['stages']['input']['state']=='succeeded'


def test_shared_resource_conflict_preserves_other_service_worker(setup,tmp_path):
    from worker_leases import ResourceBusy
    store,resource=setup
    other=CharacterStore(tmp_path/'other');other.save(new_character(IDENTITY),expected_revision=None)
    with StageExecutor(store,resource,{'fixture':adapter()}) as first, StageExecutor(other,resource,{'fixture':adapter()}) as second:
        claim=start(first,delay=600)
        with pytest.raises(ResourceBusy):
            start(second)
        assert store.load(IDENTITY)['stages']['input']['state']=='running'
        assert other.load(IDENTITY)['stages']['input']['state']=='failed'
        first.cancel(claim,grace=.1)
        retry=start(second)
        assert second.wait(retry,timeout=5)['stages']['input']['state']=='succeeded'


def test_stale_completion_preserves_correction(setup):
    from character_contracts import invalidate
    from character_coordinator import StaleClaim
    store,resource=setup
    with StageExecutor(store,resource,{'fixture':adapter()}) as service:
        claim=start(service)
        before=store.load(IDENTITY)
        corrected=invalidate(before,'input');store.save(corrected,expected_revision=before['revision'])
        with pytest.raises(StaleClaim):
            service.wait(claim,timeout=5)
        assert store.load(IDENTITY)==corrected


def test_recovery_refuses_live_parent_even_without_a_service_guard(setup):
    from character_coordinator import StageCoordinator
    from worker_leases import WorkerLease,OwnershipError
    store,resource=setup
    coordinator=StageCoordinator(store)
    claim=coordinator.start(IDENTITY,'input',{}, {'adapter':'fixture-v1'}, {},external_inputs=INPUT_HASHES)
    workspace=store.root/IDENTITY/'runs'/'input'/'1'
    lease=WorkerLease(workspace/'lease.json',resource)
    lease.start([sys.executable,'-c','import time;time.sleep(600)'])
    try:
        with pytest.raises(OwnershipError):
            StageExecutor(store,resource,{'fixture':adapter()})
        assert lease.process.poll() is None
    finally:
        lease.cancel(grace=.1)
        coordinator.end(claim,'cancelled','fixture_cleanup')
    with StageExecutor(store,resource,{'fixture':adapter()}) as service:
        retry=start(service)
        assert service.wait(retry,timeout=5)['stages']['input']['state']=='succeeded'


def test_dependency_paths_and_completed_outputs_survive_cancel(setup):
    store,resource=setup
    def inspect(context):
        assert context.inputs['input:input.png'].read_bytes()==ORIGINAL
        return [sys.executable,'-c','import time;time.sleep(600)']
    assessment=Adapter('assessment',{'adapter':'assessment-v1'},('result.json',),inspect,lambda _:Decision('accept',{}))
    with StageExecutor(store,resource,{'fixture':adapter(),'assessment':assessment}) as service:
        original=service.wait(start(service),timeout=5)
        refs=original['stages']['input']['outputs']
        claim=service.start(IDENTITY,'assessment',{}, {'input':['input.png']})
        service.cancel(claim,grace=.1)
        assert store.load(IDENTITY)['stages']['input']==original['stages']['input']
        assert all((store.root/IDENTITY/ref['path']).is_file() for ref in refs)
        assert start(service).cached


def test_wait_does_not_block_cancellation_from_another_thread(setup):
    import threading
    store,resource=setup
    with StageExecutor(store,resource,{'fixture':adapter()}) as service:
        claim=start(service,delay=600)
        waiting=threading.Event();cancelled=threading.Event();results=[]
        def wait():
            waiting.set()
            try: results.append(service.wait(claim,timeout=2))
            except subprocess.TimeoutExpired: results.append('timed_out')
        def cancel():
            service.cancel(claim,grace=.1);cancelled.set()
        waiter=threading.Thread(target=wait);waiter.start();assert waiting.wait(1)
        # Enter the blocking wait before submitting cancellation.
        time.sleep(.05)
        canceller=threading.Thread(target=cancel);canceller.start()
        try:
            assert cancelled.wait(.5),'Blocking wait held the service mutex against cancellation'
        finally:
            waiter.join(3);canceller.join(3)
        assert results[0]['stages']['input']['state']=='cancelled'


def test_uncertain_completion_blocks_new_work_and_preserves_visible_success(setup,monkeypatch):
    import character_store
    from character_store import CommitUncertain
    store,resource=setup
    service=StageExecutor(store,resource,{'fixture':adapter()})
    claim=start(service)
    original=character_store._sync_directory
    def fail_pointer_sync(path):
        if path==store.root/IDENTITY:
            raise OSError('Injected post-rename directory sync failure')
        return original(path)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(character_store,'_sync_directory',fail_pointer_sync)
            with pytest.raises(CommitUncertain):
                service.wait(claim,timeout=5)
        assert store.load(IDENTITY)['stages']['input']['state']=='succeeded'
        with pytest.raises(RuntimeError):
            start(service)
    finally:
        service.close()
    assert store.load(IDENTITY)['stages']['input']['state']=='succeeded'
    with StageExecutor(store,resource,{'fixture':adapter()}) as replacement:
        assert start(replacement).cached


def test_invalid_adapter_is_rejected_before_namespace_mutation(setup):
    store,resource=setup
    bad=Adapter('input',{},('input.png',),command,accept)
    with pytest.raises(ValueError):
        StageExecutor(store,resource,{'bad':bad})
    assert not (store.root/'.service.lock').exists()
    assert store.load(IDENTITY)['revision']==0


def test_crash_during_lease_publication_never_executes_target(setup):
    store,resource=setup
    ready=store.root.parent/'gate-ready';forbidden=store.root.parent/'must-not-execute'
    code='''import sys,time
from pathlib import Path
from hashlib import sha256
from character_store import CharacterStore
from character_executor import StageExecutor,Adapter
from character_coordinator import Decision
from worker_leases import WorkerLease
def paused_persist(self,value):
 Path(sys.argv[3]).write_text('gate blocked before durable lease')
 time.sleep(600)
WorkerLease._persist=paused_persist
def command(ctx):
 return [sys.executable,'-c',"from pathlib import Path;import sys;Path(sys.argv[1]).write_text('executed')",sys.argv[4]]
service=StageExecutor(CharacterStore(sys.argv[1]),sys.argv[2],{'fixture':Adapter('input',{'adapter':'fixture-v1'},('input.png',),command,lambda _:Decision('accept',{}))})
service.start('a'*32,'fixture',{}, {},external_inputs={'upload':sha256(b'fixture').hexdigest()})
'''
    parent=subprocess.Popen([sys.executable,'-c',code,str(store.root),str(resource),str(ready),str(forbidden)],cwd=Path(__file__).parents[1])
    try:
        deadline=time.monotonic()+5
        while not ready.exists() and time.monotonic()<deadline: time.sleep(.02)
        assert ready.exists()
        parent.kill();parent.wait(timeout=5)
        with StageExecutor(store,resource,{'fixture':adapter()}) as service:
            assert store.load(IDENTITY)['stages']['input']['state']=='interrupted'
            assert not forbidden.exists()
            retry=start(service)
            assert service.wait(retry,timeout=5)['stages']['input']['state']=='succeeded'
            assert not forbidden.exists()
    finally:
        if parent.poll() is None: parent.terminate();parent.wait(timeout=5)
