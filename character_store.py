"""Opt-in POSIX character storage. Never migrates legacy jobs or starts workers.

Immutable revisions + atomic pointer publication; locks coordinate metadata only,
not GPU ownership. Supported/tested on Linux/WSL local filesystems.
"""
from contextlib import contextmanager
from hashlib import sha256
import errno
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from uuid import uuid4

from character_contracts import DEPENDENCIES, new_character, validate_character

MAX_METADATA = 1024 * 1024


class RevisionConflict(ValueError):
    pass


class CommitUncertain(OSError):
    """Rename happened but directory durability failed; reconcile before retry."""


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class CharacterStore:
    def __init__(self, root):
        root = Path(root)
        if root.is_symlink():
            raise ValueError('Store root must not be a symlink.')
        if not root.exists():
            root.mkdir(mode=0o700)
            _sync_directory(root.parent)
        self.root = root.resolve()
        if not self.root.is_dir():
            raise ValueError('Store root must be a directory.')

    @contextmanager
    def _writer(self):
        import fcntl
        descriptor = os.open(self.root / '.writer.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError('Unsafe store lock.')
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _open(self, relative):
        # Anchor every path component to directory descriptors. No symlink can
        # redirect a record or artifact outside the chosen private namespace.
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            parts = relative.split('/')
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            result = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            if not stat.S_ISREG(os.fstat(result).st_mode):
                os.close(result)
                raise ValueError('Character files must be regular files.')
            return result
        finally:
            os.close(descriptor)

    def _read_metadata(self, relative):
        with os.fdopen(self._open(relative), 'rb') as stream:
            data = stream.read(MAX_METADATA + 1)
        if len(data) > MAX_METADATA:
            raise ValueError('Character metadata exceeds the size limit.')
        return data

    def load(self, identifier):
        new_character(identifier)  # validates identity before constructing paths
        try:
            pointer_data = self._read_metadata(f'{identifier}/current.json')
        except FileNotFoundError:
            return None
        except OSError as error:
            raise ValueError('Unsafe or unreadable character pointer.') from error
        try:
            pointer = json.loads(pointer_data)
            if (not isinstance(pointer, dict) or set(pointer) != {'revision', 'sha256'}
                    or type(pointer['revision']) is not int or pointer['revision'] < 0
                    or not isinstance(pointer['sha256'], str)
                    or not re.fullmatch('[0-9a-f]{64}', pointer['sha256'])):
                raise ValueError('Invalid character pointer.')
            relative = f"{identifier}/revisions/{pointer['revision']}-{pointer['sha256']}.json"
            data = self._read_metadata(relative)
            if sha256(data).hexdigest() != pointer['sha256']:
                raise ValueError('Character revision checksum mismatch.')
            record = validate_character(json.loads(data))
            if record['id'] != identifier or record['revision'] != pointer['revision']:
                raise ValueError('Character revision identity mismatch.')
            return record
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError('Corrupt or unavailable character revision.') from error

    def _directory(self, path):
        if path.is_symlink():
            raise ValueError('Unsafe character directory.')
        if not path.exists():
            path.mkdir(mode=0o700)
            _sync_directory(path.parent)
        if not path.is_dir():
            raise ValueError('Character directory is not a directory.')

    def _atomic(self, path, data):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
            try:
                _sync_directory(path.parent)
            except OSError as error:
                raise CommitUncertain('Publication durability uncertain; reconcile the current revision before retry.') from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save(self, record, *, expected_revision):
        record = validate_character(record)
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
            raise ValueError('Invalid expected revision.')
        encoded = json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if len(encoded) > MAX_METADATA:
            raise ValueError('Character metadata exceeds the size limit.')
        identifier = record['id']
        with self._writer():
            previous = self.load(identifier)
            revision = previous['revision'] if previous else None
            if revision != expected_revision or record['revision'] != (0 if revision is None else revision + 1):
                raise RevisionConflict('Character changed; reload before saving.')
            folder = self.root / identifier
            self._directory(folder)
            revisions = folder / 'revisions'
            self._directory(revisions)
            for stage in record['stages'].values():
                if stage['state'] == 'succeeded' and not self.reusable(identifier, stage, stage['fingerprint']):
                    raise ValueError('Successful output artifacts failed byte verification.')
            digest = sha256(encoded).hexdigest()
            target = revisions / f"{record['revision']}-{digest}.json"
            if target.exists() or target.is_symlink():
                if self._read_metadata(f'{identifier}/revisions/{target.name}') != encoded:
                    raise ValueError('Existing immutable revision is corrupt.')
            else:
                self._atomic(target, encoded)
            pointer = json.dumps({'revision': record['revision'], 'sha256': digest}, sort_keys=True).encode()
            self._atomic(folder / 'current.json', pointer)

    def reusable(self, identifier, stage, expected_fingerprint):
        try:
            probe = new_character(identifier)
            probe['stages']['input'] = stage
            validate_character(probe)
            if stage['state'] != 'succeeded' or stage['fingerprint'] != expected_fingerprint:
                return False
            for artifact in stage['outputs']:
                with os.fdopen(self._open(f"{identifier}/{artifact['path']}"), 'rb') as stream:
                    if os.fstat(stream.fileno()).st_size != artifact['bytes']:
                        return False
                    digest = sha256()
                    while data := stream.read(1024 * 1024):
                        digest.update(data)
                    if digest.hexdigest() != artifact['sha256']:
                        return False
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def publish_artifacts(self, identifier, stage, attempt, source_dir, names):
        """Publish trusted worker files, without accepting or updating a stage.

        Source directory is server-selected, never an HTTP request path. The
        coordinator must validate outputs and separately save with revision CAS.
        """
        if not isinstance(stage, str) or stage not in DEPENDENCIES or type(attempt) is not int or attempt < 1:
            raise ValueError('Invalid artifact stage or attempt.')
        if (not isinstance(names, (list, tuple)) or not 0 < len(names) <= 64
                or not all(isinstance(name, str) and re.fullmatch('[a-zA-Z0-9_][a-zA-Z0-9_.-]*', name) for name in names)
                or len(set(names)) != len(names)):
            raise ValueError('Use unique generated artifact filenames without directory components.')
        if self.load(identifier) is None:
            raise ValueError('Create the character record before publishing artifacts.')
        source_dir = Path(source_dir)
        if source_dir.is_symlink():
            raise ValueError('Worker source directory must not be a symlink.')
        directory = None
        sources = []
        try:
            directory = os.open(source_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            for name in names:
                try:
                    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                except OSError as error:
                    if error.errno == errno.ELOOP:
                        raise ValueError('Worker artifacts must not be symlinks.') from error
                    raise
                sources.append((name, descriptor))
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise ValueError('Worker artifacts must be regular files.')
            # Directory setup only holds the metadata lock briefly. Copying does
            # not block metadata reads/writes; the later CAS detects stale work.
            with self._writer():
                folder = self.root / identifier
                artifacts = folder / 'artifacts'
                self._directory(artifacts)
                phase = artifacts / stage
                self._directory(phase)
                temporary = Path(tempfile.mkdtemp(prefix='.publishing-', dir=phase))
            final = phase / f'{attempt}-{uuid4().hex}'
            results = []
            for name, descriptor in sources:
                before = os.fstat(descriptor)
                digest = sha256()
                copied = 0
                target = os.open(temporary / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(target, 'wb') as destination:
                    while data := os.read(descriptor, min(1024 * 1024, before.st_size - copied + 1)):
                        copied += len(data)
                        if copied > before.st_size:
                            raise ValueError('Worker artifact changed during publication.')
                        destination.write(data)
                        digest.update(data)
                    destination.flush()
                    os.fsync(destination.fileno())
                after = os.fstat(descriptor)
                if copied != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('Worker artifact changed during publication.')
                results.append({'path': (final / name).relative_to(folder).as_posix(), 'sha256': digest.hexdigest(), 'bytes': copied})
            _sync_directory(temporary)
            if final.exists():
                raise ValueError('Published attempt identity already exists.')
            os.rename(temporary, final)
            try:
                _sync_directory(phase)
            except OSError as error:
                raise CommitUncertain('Artifact publication durability uncertain; reconcile before retry.') from error
            return results
        finally:
            # Failed directories remain private and unreferenced for inspection;
            # source files and previous completed attempts are never deleted.
            for _, descriptor in sources:
                os.close(descriptor)
            if directory is not None:
                os.close(directory)
