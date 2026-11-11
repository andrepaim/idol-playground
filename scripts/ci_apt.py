"""Hosted-runner-only Ubuntu mirror fallback; never skip browser dependencies."""
import os
from pathlib import Path
import stat
import tempfile
from urllib.parse import urlsplit

OPTIONS = 'Acquire::Retries "2";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n'
CANONICAL = 'https://archive.ubuntu.com/ubuntu'


def _write(path, text):
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def configure(mirror_list, apt_options):
    mirror_list, apt_options = Path(mirror_list), Path(apt_options)
    if mirror_list.is_symlink() or apt_options.is_symlink():
        raise ValueError('CI APT configuration must not use symlinks.')
    mirrors = None
    if mirror_list.exists():
        lines = []
        has_canonical = False
        for line in mirror_list.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                lines.append(line)
                continue
            parsed = urlsplit(stripped.split()[0])
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Unsupported runner mirror entry; inspect APT configuration.')
            if parsed.hostname == 'azure.archive.ubuntu.com':
                continue
            has_canonical |= parsed.hostname == 'archive.ubuntu.com'
            lines.append(line)
        if not has_canonical:
            lines.append(CANONICAL)
        mirrors = '\n'.join(lines) + '\n'
    # Parse and validate all input before changing either destination.
    if mirrors is not None:
        _write(mirror_list, mirrors)
    _write(apt_options, OPTIONS)


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('This helper configures disposable GitHub Actions runners only.')
    configure('/etc/apt/apt-mirrors.txt', '/etc/apt/apt.conf.d/99-idol-network')
    print('Configured canonical Ubuntu archive fallback and bounded APT network requests; package verification remains enabled.')


if __name__ == '__main__':
    main()
