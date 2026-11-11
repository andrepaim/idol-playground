"""Linux cooperating-worker ownership. Not yet connected to app/model launchers.

Workers must preserve identity markers/resource FD and clean their descendants
on termination. Recovery never signals an identity it cannot verify.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from uuid import uuid4


class ResourceBusy(RuntimeError):
    pass


class OwnershipError(RuntimeError):
    pass


def _boot_hash():
    return sha256(Path('/proc/sys/kernel/random/boot_id').read_bytes()).hexdigest()


def _identity(pid):
    try:
        root = Path(f'/proc/{pid}')
        values = (root/'stat').read_text().rsplit(')', 1)[1].split()
        return {'pid':pid, 'start_ticks':int(values[19]), 'boot_hash':_boot_hash(), 'uid':root.stat().st_uid, 'terminal':values[0] == 'Z'}
    except (OSError, ValueError, IndexError):
        return None


def _same(actual, expected):
    return actual is not None and all(actual[key] == expected[key] for key in ('pid','start_ticks','boot_hash','uid'))


def _markers(pid, record):
    try:
        values = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
        return (f"IDOL_LEASE_NONCE={record['nonce']}".encode() in values
                and f"IDOL_LEASE_NAMESPACE={record['namespace']}".encode() in values)
    except OSError:
        return False


def _private_log(path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb')


class WorkerLease:
    def __init__(self, lease_file, resource_file):
        if sys.platform != 'linux' or not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
            raise RuntimeError('Worker leases require Linux/WSL procfs and pidfd support.')
        self.path, self.resource = Path(lease_file), Path(resource_file)
        if self.path.is_symlink() or self.resource.is_symlink():
            raise ValueError('Lease and resource files must not be symlinks.')
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.resource.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.path = self.path.parent.resolve() / self.path.name
        self.resource = self.resource.parent.resolve() / self.resource.name
        self.namespace = sha256(str(self.path).encode()).hexdigest()
        self.resource_hash = sha256(str(self.resource).encode()).hexdigest()
        self.process = None
        self._fd = None
        self._nonce = None

    def _persist(self, value):
        if self.path.is_symlink():
            raise ValueError('Unsafe lease destination.')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(value, stream, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _read(self):
        descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Lease must be a regular file.')
            data = stream.read(65537)
        if len(data) > 65536:
            raise ValueError('Lease is oversized.')
        record = json.loads(data)
        if (not isinstance(record, dict) or type(record.get('schema_version')) is not int or record.get('schema_version') != 1
                or record.get('namespace') != self.namespace or record.get('resource') != self.resource_hash
                or not isinstance(record.get('nonce'), str) or not re.fullmatch('[0-9a-f]{32}', record['nonce'])):
            raise ValueError('Unsupported or mismatched worker lease.')
        for role in ('parent', 'worker'):
            identity = record.get(role)
            if (not isinstance(identity, dict) or type(identity.get('pid')) is not int or identity['pid'] < (2 if role == 'worker' else 1)
                    or type(identity.get('start_ticks')) is not int or identity['start_ticks'] < 0
                    or type(identity.get('uid')) is not int or identity['uid'] != os.getuid()
                    or not isinstance(identity.get('boot_hash'), str) or not re.fullmatch('[0-9a-f]{64}', identity['boot_hash'])):
                raise ValueError('Invalid worker process identity.')
        if self._nonce is not None and record['nonce'] != self._nonce:
            raise OwnershipError('Lease identity changed; refusing to signal a process.')
        return record

    def _close_resource(self):
        if self._fd is not None:
            os.close(self._fd)  # do not LOCK_UN: a child may still hold this OFD
            self._fd = None

    def start(self, command, *, env=None):
        import fcntl
        if self.process is not None or self.path.exists():
            raise ValueError('Each attempt needs a new lease identity.')
        if not isinstance(command, (list, tuple)) or not command or not all(isinstance(value, str) and '\0' not in value for value in command):
            raise ValueError('Use a registered argv command, never a shell string.')
        self._fd = os.open(self.resource, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        if not stat.S_ISREG(os.fstat(self._fd).st_mode):
            self._close_resource()
            raise ValueError('Resource lock must be a regular file.')
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._close_resource()
            raise ResourceBusy('A cooperating worker still owns the resource.') from error
        except OSError:
            self._close_resource()
            raise
        read_gate, write_gate = os.pipe()
        self._nonce = uuid4().hex
        environment = {**(os.environ if env is None else env), 'IDOL_LEASE_NONCE':self._nonce,
                       'IDOL_LEASE_NAMESPACE':self.namespace, 'IDOL_RESOURCE_FD':str(self._fd)}
        try:
            with _private_log(self.path.with_suffix('.stdout.log')) as stdout, _private_log(self.path.with_suffix('.stderr.log')) as stderr:
                self.process = subprocess.Popen([sys.executable, '-I', '-S', str(Path(__file__).parent/'scripts/worker_gate.py'),
                    '--gate',str(read_gate),'--resource',str(self._fd),'--parent',str(os.getpid()),'--',*command],
                    stdout=stdout, stderr=stderr, env=environment, start_new_session=True, pass_fds=(read_gate,self._fd))
            identity = _identity(self.process.pid)
            if identity is None:
                raise OwnershipError('Worker exited before ownership was recorded.')
            record = {'schema_version':1,'namespace':self.namespace,'resource':self.resource_hash,'nonce':self._nonce,
                      'parent':_identity(os.getpid()),'worker':identity,'state':'running',
                      'command_sha256':sha256(json.dumps(list(command)).encode()).hexdigest(),
                      'started_at':datetime.now(timezone.utc).isoformat()}
            self._persist(record)
            os.write(write_gate, b'G')
            return self.process
        except BaseException:
            os.close(write_gate)
            write_gate = None
            if self.process is not None:
                self.process.wait(timeout=5)  # EOF gate prevents target execution
            self._close_resource()
            raise
        finally:
            os.close(read_gate)
            if write_gate is not None:
                os.close(write_gate)

    def _owned(self, record):
        results = []
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():
                continue
            pid = int(path.name)
            identity = _identity(pid)
            if identity and not identity['terminal'] and identity['uid'] == os.getuid() and _markers(pid, record):
                results.append(identity)
        return results

    def _signal(self, identity, record, signum):
        descriptor = None
        try:
            descriptor = os.pidfd_open(identity['pid'])
            actual = _identity(identity['pid'])
            if _same(actual, identity) and not actual['terminal'] and _markers(identity['pid'], record):
                signal.pidfd_send_signal(descriptor, signum)
        except ProcessLookupError:
            pass
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _stop_owned(self, record, grace):
        if type(grace) not in (int, float) or not math.isfinite(grace) or not 0 <= grace <= 30:
            raise ValueError('Grace period must be finite and between zero and 30 seconds.')
        owned = self._owned(record)
        for identity in owned:
            self._signal(identity, record, signal.SIGTERM)
        deadline = time.monotonic() + grace
        while self._owned(record) and time.monotonic() < deadline:
            time.sleep(.02)
        for identity in self._owned(record):
            self._signal(identity, record, signal.SIGKILL)
        deadline = time.monotonic() + 5
        while self._owned(record) and time.monotonic() < deadline:
            time.sleep(.02)
        if self._owned(record):
            raise OwnershipError('Owned worker has not exited; resource ownership is retained.')

    def wait(self, *, timeout=None):
        if self.process is None:
            raise OwnershipError('No worker was launched by this manager.')
        code = self.process.wait(timeout=timeout)
        record = self._read()
        self._stop_owned(record, .2)
        record.update(state='exited', returncode=code, finished_at=datetime.now(timezone.utc).isoformat())
        try:
            self._persist(record)
        finally:
            self._close_resource()
        return record

    def cancel(self, *, grace=2):
        if self.process is None:
            raise OwnershipError('Only the launching manager may cancel a live parent-owned worker.')
        record = self._read()
        actual = _identity(record['worker']['pid'])
        if actual and not actual['terminal'] and (not _same(actual, record['worker']) or not _markers(actual['pid'], record)):
            raise OwnershipError('Worker identity is foreign or reused; no signal sent.')
        self._stop_owned(record, grace)
        code = self.process.wait(timeout=5)
        record.update(state='cancelled', returncode=code, finished_at=datetime.now(timezone.utc).isoformat())
        try:
            self._persist(record)
        finally:
            self._close_resource()
        return record

    def recover(self, *, grace=2):
        record = self._read()
        parent = _identity(record['parent']['pid'])
        if _same(parent, record['parent']) and not parent['terminal']:
            raise OwnershipError('Original parent is alive; do not steal its worker.')
        actual = _identity(record['worker']['pid'])
        if actual and not actual['terminal'] and (not _same(actual, record['worker']) or not _markers(actual['pid'], record)):
            raise OwnershipError('Worker identity is foreign or reused; no signal sent.')
        self._stop_owned(record, grace)
        record.update(state='interrupted', recovered_at=datetime.now(timezone.utc).isoformat())
        self._persist(record)
        return record
