"""Opt-in Linux application reservation shared by cooperating local instances.

Closing an owner's FD must not unlock the same open-file description inherited
by a registered worker. This module never signals another process or deletes a
lock file. Per-worker leases remain separate.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import sys

_current=None


class ReservationBusy(RuntimeError):
    pass


def default_resource():
    configured=os.environ.get('IDOL_GPU_RESOURCE')
    if configured:return Path(configured)
    cache=Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))
    return cache/'idol-playground/cuda.lock'


class Reservation:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else default_resource()
        if not self.path.is_absolute():raise ValueError('GPU reservation requires an absolute resource path.')
        self._fd=None
        self._identity=None

    @staticmethod
    def _safe(info):
        return (stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
                and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and info.st_size==0)

    def acquire(self):
        if sys.platform!='linux':raise RuntimeError('Application GPU reservation requires Linux/WSL.')
        if self._fd is not None:raise RuntimeError('This reservation is already acquired.')
        import fcntl
        self.path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        self.path=self.path.parent.resolve()/self.path.name
        descriptor=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
        try:
            info=os.fstat(descriptor)
            visible=self.path.lstat()
            if not self._safe(info) or (visible.st_dev,visible.st_ino)!=(info.st_dev,info.st_ino):
                raise ValueError('Unsafe GPU reservation file; preserve it and correct the configuration.')
            try:fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                raise ReservationBusy('Another application or inherited worker reserves the GPU. Let its work finish or close the owning app.') from None
        except BaseException:
            os.close(descriptor)
            raise
        self._fd=descriptor
        self._identity=(info.st_dev,info.st_ino)
        return self

    @property
    def fd(self):
        if self._fd is None:raise RuntimeError('GPU reservation is not acquired.')
        info=os.fstat(self._fd)
        visible=self.path.lstat()
        if (not self._safe(info) or not self._safe(visible)
                or (info.st_dev,info.st_ino)!=self._identity
                or (visible.st_dev,visible.st_ino)!=self._identity):
            raise RuntimeError('GPU reservation identity changed; refusing to launch work.')
        return self._fd

    def close(self):
        if self._fd is not None:
            descriptor,self._fd=self._fd,None
            info=os.fstat(descriptor)
            if (info.st_dev,info.st_ino)!=self._identity:
                raise RuntimeError('GPU reservation descriptor changed; refusing to close an unknown file.')
            os.close(descriptor)  # no LOCK_UN: an inherited worker may still hold this OFD

    def __enter__(self):
        return self.acquire()

    def __exit__(self,*error):
        self.close()


@contextmanager
def application_reservation(path=None):
    global _current
    with Reservation(path) as reservation:
        if _current is not None:raise RuntimeError('An application reservation is already registered in this process.')
        _current=reservation
        try:yield reservation
        finally:_current=None


def inherited_fds():
    """Only explicitly registered direct launchers receive this descriptor."""
    return () if _current is None else (_current.fd,)
