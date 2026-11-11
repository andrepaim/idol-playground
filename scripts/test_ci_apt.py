"""Fixture-only CI mirror tests; never reads/writes /etc on the owner machine."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ci_apt import configure


class MirrorTests(unittest.TestCase):
    def test_removes_failing_mirror_preserving_valid_entries_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mirror, options = root/'mirrors', root/'options'
            mirror.write_text('# runner mirrors\nhttp://azure.archive.ubuntu.com/ubuntu priority:1\nhttps://archive.ubuntu.com/ubuntu priority:2\nhttps://security.ubuntu.com/ubuntu priority:3\n')
            mirror.chmod(0o644)
            configure(mirror, options)
            text = mirror.read_text()
            self.assertNotIn('azure.archive.ubuntu.com', text)
            self.assertIn('https://archive.ubuntu.com/ubuntu priority:2', text)
            self.assertIn('https://security.ubuntu.com/ubuntu priority:3', text)
            self.assertEqual(mirror.stat().st_mode & 0o777, 0o644)
            self.assertIn('Acquire::http::Timeout "30";', options.read_text())
            self.assertNotIn('AllowUnauthenticated', options.read_text())

    def test_adds_canonical_fallback_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mirror, options = root/'mirrors', root/'options'
            mirror.write_text('http://azure.archive.ubuntu.com/ubuntu\n')
            configure(mirror, options)
            first = mirror.read_text(), options.read_text()
            self.assertIn('https://archive.ubuntu.com/ubuntu', first[0])
            configure(mirror, options)
            self.assertEqual(first, (mirror.read_text(), options.read_text()))

    def test_no_mirror_list_keeps_runner_sources_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configure(root/'absent', root/'options')
            self.assertFalse((root/'absent').exists())
            self.assertTrue((root/'options').is_file())

    def test_malformed_or_symlink_inputs_are_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mirror, options = root/'mirrors', root/'options'
            for value in ['not a mirror\n', 'https://\n', 'https://user:secret@archive.ubuntu.com/ubuntu\n']:
                mirror.write_text(value)
                with self.assertRaises(ValueError):
                    configure(mirror, options)
                self.assertEqual(mirror.read_text(), value)
                self.assertFalse(options.exists())
            target = root/'original'
            target.write_text('unchanged')
            mirror.unlink()
            mirror.symlink_to(target)
            with self.assertRaises(ValueError):
                configure(mirror, options)
            self.assertEqual(target.read_text(), 'unchanged')

    def test_cli_refuses_owner_machine_configuration(self):
        environment = {k:v for k,v in os.environ.items() if k != 'GITHUB_ACTIONS'}
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('ci_apt.py'))], env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('GitHub', result.stderr)


if __name__ == '__main__':
    unittest.main()
