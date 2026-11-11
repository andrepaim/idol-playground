"""Exercise the unbundled renderer used to supply neural stereo inputs."""
from argparse import Namespace
import json
from pathlib import Path

from PIL import Image

from experiments.splat_mesh.render_views import capture_views
from test_browser import splat_bytes


def test_calibrated_capture_records_installed_renderer_and_nonempty_views(tmp_path):
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / 'synthetic.ply'
    source.write_bytes(splat_bytes())
    output = tmp_path / 'views'
    manifest = capture_views(Namespace(splat=source, output=output,
                                       base_url='http://splat-mesh.local/', withheld=False))

    assert len(manifest['pairs']) == 36
    assert manifest == json.loads((output / 'views.json').read_text())
    for pair in manifest['pairs']:
        for camera in pair.values():
            with Image.open(output / camera['file']) as image:
                assert image.size == (512, 512)
                assert image.getchannel('A').getbbox() is not None
            assert len(camera['extrinsic']) == 4
            assert camera['baseline'] > 0
            assert camera['focal'] > 0

    for package in ('three', '@mkkellogg/gaussian-splats-3d'):
        installed = json.loads((root / 'node_modules' / package / 'package.json').read_text())
        assert installed['version'] in manifest['renderer']
