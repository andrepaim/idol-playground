"""Opt-in stage execution for registered cooperating Linux workers.

No HTTP routes, external reasoning or legacy inference adapters are enabled here.
"""
from copy import deepcopy
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import re
import stat
import threading

from character_contracts import DEPENDENCIES, fingerprint
from character_coordinator import Claim, StageCoordinator, StaleClaim
from character_store import CommitUncertain
from worker_leases import WorkerLease


class ServiceBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class Adapter:
    stage: str
    versions: dict
    names: tuple
    command: object
    validator: object
    contextual: bool = False


@dataclass(frozen=True)
class Context:
    claim: Claim
    workspace: Path
    parameters: dict
    inputs: dict


@dataclass
class _Run:
    claim: Claim
    lease: WorkerLease
    workspace: Path
    adapter: Adapter
    context: Context


class StageExecutor:
    def __init__(self, store, resource_file, adapters):
        self.store = store
        self.coordinator = StageCoordinator(store)
        self.resource = Path(resource_file)
        self.adapters = {}
        for key, adapter in adapters.items():
            if (not isinstance(key, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}', key)
                    or not isinstance(adapter, Adapter) or adapter.stage not in DEPENDENCIES
                    or not adapter.versions or not callable(adapter.command) or not callable(adapter.validator)
                    or type(adapter.contextual) is not bool
                    or not isinstance(adapter.names, tuple) or not 0 < len(adapter.names) <= 64
                    or not all(isinstance(name, str) and re.fullmatch('[a-zA-Z0-9_][a-zA-Z0-9_.-]*', name) for name in adapter.names)
                    or len(set(adapter.names)) != len(adapter.names) or {'_execution.json','_validation.json'}.intersection(adapter.names)):
                raise ValueError('Adapters must be explicit trusted code with unique generated output names.')
            fingerprint(adapter.stage, {}, {}, adapter.versions)
            self.adapters[key] = Adapter(adapter.stage, deepcopy(adapter.versions), adapter.names, adapter.command, adapter.validator, adapter.contextual)
        self._mutex = threading.RLock()
        self._runs = {}
        self._closed = False
        self._blocked = False
        self._guard = os.open(store.root/'.service.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(self._guard).st_mode):
                raise ValueError('Unsafe service lock.')
            try:
                fcntl.flock(self._guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ServiceBusy('Another stage service owns this private character namespace.') from error
            self._recover()
        except BaseException:
            os.close(self._guard)
            self._guard = None
            raise

    def _workspace(self, claim):
        return self.store.root/claim.identifier/'runs'/claim.stage/str(claim.attempt)

    def _recover(self):
        # Only the current accepted pointer identifies a running attempt. Orphan
        # revision files are never promoted by choosing the highest counter.
        for path in sorted(self.store.root.iterdir()):
            if not re.fullmatch('[0-9a-f]{32}', path.name):
                continue
            record = self.store.load(path.name)
            if record is None:
                continue
            running = [(name,value) for name,value in record['stages'].items() if value['state'] == 'running']
            if len(running) > 1:
                raise ValueError('Multiple running stages require explicit reconciliation.')
            for name, value in running:
                if value['attempt'] < 1 or value['fingerprint'] is None:
                    raise ValueError('Running stage lacks a verifiable attempt identity.')
                claim = Claim(path.name,name,value['attempt'],value['fingerprint'],())
                lease_path = self._workspace(claim)/'lease.json'
                lease = WorkerLease(lease_path,self.resource)
                if lease_path.exists():
                    lease.recover()
                else:
                    # A crash can occur after the stage CAS, before launch or
                    # lease publication. An ungranted bootstrap cannot execute;
                    # the shared resource must still be proven idle first.
                    lease.verify_idle()
                self.coordinator.end(claim,'interrupted','service_restart')

    def _ready(self):
        if self._closed or self._blocked:
            raise RuntimeError('Stage service is closed or needs uncertain-commit reconciliation.')

    def start(self, identifier, adapter_key, parameters, input_names, *, external_inputs=None):
        with self._mutex:
            self._ready()
            if adapter_key not in self.adapters:
                raise ValueError('Choose a registered adapter.')
            adapter = self.adapters[adapter_key]
            parameters, input_names = deepcopy(parameters), deepcopy(input_names)
            versions = {**adapter.versions,'executor':'v1','registered_adapter':adapter_key}
            if adapter.contextual:
                versions['context_validation'] = 'v1'
            try:
                claim = self.coordinator.start(identifier,adapter.stage,parameters,versions,input_names,external_inputs=external_inputs)
            except CommitUncertain:
                self._blocked = True
                raise
            if claim.cached:
                return claim
            lease = None
            try:
                workspace = self._workspace(claim)
                for folder in (workspace.parent.parent,workspace.parent):
                    self.store._directory(folder)
                if workspace.exists() or workspace.is_symlink():
                    raise ValueError('Attempt workspace already exists; preserve and reconcile it.')
                self.store._directory(workspace)
                lease = WorkerLease(workspace/'lease.json',self.resource)
                inputs = {}
                record = self.store.load(identifier)
                for dependency,names in input_names.items():
                    for name in names:
                        matches = [item for item in record['stages'][dependency]['outputs'] if Path(item['path']).name == name]
                        inputs[f'{dependency}:{name}'] = self.store.root/identifier/matches[0]['path']
                context = Context(claim,workspace,deepcopy(parameters),deepcopy(inputs))
                argv = adapter.command(Context(claim,workspace,deepcopy(parameters),deepcopy(inputs)))
                self._runs[(identifier,claim.stage,claim.attempt)] = _Run(claim,lease,workspace,adapter,context)
                lease.start(argv)
                return claim
            except BaseException:
                if lease is not None and lease.process is not None:
                    if lease.process.poll() is None:
                        lease.cancel()
                    else:
                        lease.process.wait(timeout=5)
                        lease._close_resource()
                        lease._confirm_resource_released()
                self._end(claim,'failed','launch_failed')
                self._runs.pop((identifier,claim.stage,claim.attempt),None)
                raise

    def _end(self, claim, state, code):
        try:
            return self.coordinator.end(claim,state,code)
        except CommitUncertain:
            self._blocked = True
            raise

    def _run(self, claim):
        run = self._runs.get((claim.identifier,claim.stage,claim.attempt))
        if run is None or run.claim is not claim:
            raise ValueError('This live execution handle does not belong to this service.')
        return run

    def wait(self, claim, *, timeout=None):
        with self._mutex:
            self._ready()
            if claim.cached:
                record = self.store.load(claim.identifier)
                if record is None or not self.store.reusable(claim.identifier,record['stages'][claim.stage],claim.fingerprint):
                    raise StaleClaim('Cached output changed; do not report an old result.')
                return record
            run = self._run(claim)
        # A blocking child wait must not hold the service mutex: cancellation
        # and shutdown need to stop/reap the worker from another caller.
        run.lease.process.wait(timeout=timeout)
        with self._mutex:
            if self._runs.get((claim.identifier,claim.stage,claim.attempt)) is not run:
                record = self.store.load(claim.identifier)
                current = record['stages'][claim.stage] if record else None
                if (current and current['attempt'] == claim.attempt and current['fingerprint'] == claim.fingerprint
                        and current['state'] in ('succeeded','failed','cancelled','interrupted','awaiting_review')):
                    return record
                raise StaleClaim('Execution was superseded during the wait.')
            result = run.lease.wait(timeout=timeout)  # timeout retains ownership
            if result['returncode'] != 0:
                record = self._end(claim,'failed','worker_exit')
            else:
                try:
                    validator = run.adapter.validator
                    if run.adapter.contextual:
                        validator = lambda paths: run.adapter.validator(deepcopy(run.context),paths)
                    record = self.coordinator.finish(claim,run.workspace,run.adapter.names,validator)
                except CommitUncertain:
                    self._blocked = True
                    raise
                except Exception:
                    try:
                        self._end(claim,'failed','output_validation_failed')
                    except StaleClaim:
                        pass  # already rejected, failed or superseded; do not overwrite
                    self._runs.pop((claim.identifier,claim.stage,claim.attempt),None)
                    raise
            self._runs.pop((claim.identifier,claim.stage,claim.attempt),None)
            return record

    def cancel(self, claim, *, grace=2):
        with self._mutex:
            self._ready()
            run = self._run(claim)
            run.lease.cancel(grace=grace)
            record = self._end(claim,'cancelled','user_cancelled')
            self._runs.pop((claim.identifier,claim.stage,claim.attempt),None)
            return record

    def close(self):
        with self._mutex:
            if self._closed:
                return
            for key,run in list(self._runs.items()):
                if run.lease.process is not None:
                    run.lease.cancel()
                try:
                    self._end(run.claim,'cancelled','service_shutdown')
                except StaleClaim:
                    pass  # completion/correction may already be visible
                self._runs.pop(key)
            os.close(self._guard)
            self._guard = None
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
