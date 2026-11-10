"""Keep CPU setup usable without replacing the preferred CUDA server environment."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class LauncherTests(unittest.TestCase):
    def test_prefers_local_environment_and_falls_back_to_checks(self):
        launcher=(Path(__file__).resolve().parent.parent/'run.sh').read_text()
        for local in (False,True):
            with self.subTest(local=local),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                (root/'run.sh').write_text(launcher)
                (root/'dist').mkdir()
                (root/'dist/index.html').write_text('fixture')
                for name in (['.venv-check','.venv'] if local else ['.venv-check']):
                    command=root/name/'bin/uvicorn'
                    command.parent.mkdir(parents=True)
                    command.write_text('#!/bin/sh\nprintf "%s\\n" "'+name+'" "$@"\n')
                    command.chmod(0o755)
                result=subprocess.run(['bash','run.sh'],cwd=root,env={**os.environ,'PORT':'8017'},capture_output=True,text=True,check=True)
                self.assertEqual('.venv' if local else '.venv-check',result.stdout.splitlines()[0])
                self.assertIn('8017',result.stdout)
                self.assertIn('127.0.0.1',result.stdout)
