"""Real Chromium acceptance against built UI; API and splats are synthetic."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import math
import json
import struct
import threading

from PIL import Image
from playwright.sync_api import sync_playwright, expect
import pytest


@pytest.fixture(scope='module')
def site():
    root = Path(__file__).resolve().parents[2] / 'dist'
    assert (root / 'index.html').is_file(), 'Run npm run build first'
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def do_GET(self):
            if self.path in ('/fixture.ply', '/fixture.glb'):
                data = mesh_bytes() if self.path.endswith('.glb') else splat_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                super().do_GET()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()
    thread.join()


def splat_bytes():
    names = ['x', 'y', 'z', 'nx', 'ny', 'nz', 'f_dc_0', 'f_dc_1', 'f_dc_2',
             'opacity', 'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3']
    header = 'ply\nformat binary_little_endian 1.0\nelement vertex 128\n'
    header += ''.join(f'property float {name}\n' for name in names) + 'end_header\n'
    rows = []
    for i in range(128):
        angle = i * math.pi / 32
        rows.append(struct.pack('<17f', math.sin(angle) * .3, (i % 8) * .04, math.cos(angle) * .3,
                                0, 0, 0, 1, 0, 0, 5, -4, -4, -4, 1, 0, 0, 0))
    return header.encode() + b''.join(rows)


def mesh_bytes():
    image = BytesIO()
    Image.new('RGB', (512, 512), 'coral').save(image, format='PNG')
    binary = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0) + struct.pack('<6f', 0, 0, 1, 0, 0, 1) + struct.pack('<3H', 0, 1, 2) + b'\0\0' + image.getvalue()
    document = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
                'buffers': [{'byteLength': len(binary)}],
                'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 36},
                                {'buffer': 0, 'byteOffset': 36, 'byteLength': 24},
                                {'buffer': 0, 'byteOffset': 60, 'byteLength': 6},
                                {'buffer': 0, 'byteOffset': 68, 'byteLength': len(image.getvalue())}],
                'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3', 'min': [0,0,0], 'max': [1,1,0]},
                              {'bufferView': 1, 'componentType': 5126, 'count': 3, 'type': 'VEC2'},
                              {'bufferView': 2, 'componentType': 5123, 'count': 3, 'type': 'SCALAR'}],
                'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'TEXCOORD_0': 1}, 'indices': 2, 'material': 0}]}],
                'images': [{'bufferView': 3, 'mimeType': 'image/png'}], 'textures': [{'source': 0}],
                'materials': [{'doubleSided': True, 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'metallicFactor': 0}}]}
    encoded = json.dumps(document).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary += bytes(-len(binary) % 4)
    chunks = struct.pack('<I4s', len(encoded), b'JSON') + encoded + struct.pack('<I4s', len(binary), b'BIN\0') + binary
    return struct.pack('<4sII', b'glTF', 2, len(chunks) + 12) + chunks


@pytest.fixture
def browser_page(site):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=['--no-sandbox', '--enable-unsafe-swiftshader'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        state = {'phase': 'sampling', 'ready': True, 'mesh_ready': True, 'submissions': 0, 'output_type': 'splat'}

        def api(route):
            path = route.request.url.split('/api/')[1]
            if path == 'status':
                route.fulfill(json={'ready': state['ready'], 'weights_downloaded': True, 'mesh': {'ready': state['mesh_ready'], 'weights_downloaded': True}})
            elif path == 'generate':
                state['output_type'] = 'mesh' if b'name="output_type"\r\n\r\nmesh' in route.request.post_data_buffer else 'splat'
                state['submissions'] += 1
                route.fulfill(status=202, json={'id': 'fixture'})
            elif path.endswith('/cancel'):
                state['phase'] = 'cancelled'
                route.fulfill(status=202, json={'state': 'cancelling'})
            else:
                phase = state['phase']
                job = {'stage': phase, 'state': 'running', 'message': 'Generating synthetic fixture',
                       'step': 4, 'total_steps': 10, 'elapsed_seconds': 12,
                       'eta_seconds': 45, 'eta_basis': 'measured'}
                if phase == 'cancelled':
                    job.update(state='cancelled', message='Generation cancelled')
                if phase == 'error':
                    job.update(state='error', message='Synthetic GPU failure')
                if phase == 'complete':
                    job.update(state='complete', seconds=20, settings={'num_gaussians': 128, 'seed': 42},
                               files={'object.ply': '/fixture.ply'})
                    if state['output_type'] == 'mesh':
                        job.update(output_type='mesh', mesh={'triangles': 1, 'texture_resolution': 512}, files={'object.glb': '/fixture.glb'})
                route.fulfill(json=job)

        page.route('**/api/**', api)
        page.goto(site)
        yield page, state
        assert not errors, errors
        browser.close()


def upload(page):
    image = BytesIO()
    Image.new('RGB', (32, 32), 'orange').save(image, format='PNG')
    page.locator('#image').set_input_files({'name': 'synthetic.png', 'mimeType': 'image/png', 'buffer': image.getvalue()})


def test_progress_download_and_repeated_viewer(browser_page):
    page, state = browser_page
    expect(page.locator('#generate')).to_be_disabled()
    upload(page)
    page.locator('#generate').click()
    expect(page.locator('#step-detail')).to_have_text('Sampling step 4 of 10')
    expect(page.locator('#eta')).to_contain_text('remaining')
    expect(page.locator('#generation-bar')).to_have_attribute('value', '4')
    expect(page.locator('[data-stage=sampling]')).to_have_attribute('aria-current', 'step')
    state['phase'] = 'complete'
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#viewer canvas')).to_have_count(1)
    expect(page.locator('#message')).to_be_hidden()
    with page.expect_download() as info:
        page.locator('#download').click()
    assert Path(info.value.path()).read_bytes().startswith(b'ply\n')
    page.locator('#generate').click()
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#viewer canvas')).to_have_count(1)
    assert state['submissions'] == 2
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_failure_releases_controls_for_retry(browser_page):
    page, state = browser_page
    state['phase'] = 'error'
    upload(page)
    page.locator('#generate').click()
    expect(page.locator('#message')).to_contain_text('Synthetic GPU failure')
    expect(page.locator('#generate')).to_be_enabled()
    expect(page.locator('#download')).to_be_hidden()
    state['phase'] = 'complete'
    page.locator('#generate').click()
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#download')).to_be_visible()


def test_missing_model_setup_and_invalid_upload(browser_page):
    page, state = browser_page
    state['ready'] = False
    page.reload()
    expect(page.locator('#setup')).to_be_visible()
    upload(page)
    expect(page.locator('#generate')).to_be_disabled()
    page.locator('#image').set_input_files({'name': 'bad.gif', 'mimeType': 'image/gif', 'buffer': b'bad'})
    expect(page.locator('#message')).to_contain_text('PNG, JPEG, or WebP')


def test_mesh_controls_download_and_switch_back_to_splat(browser_page):
    page, state = browser_page
    page.locator('#output_type').select_option('mesh')
    upload(page)
    expect(page.locator('#mode')).to_be_disabled()
    expect(page.locator('#target_faces')).to_be_enabled()
    state['phase'] = 'extract'
    page.locator('#generate').click()
    expect(page.locator('#step-detail')).to_contain_text('Surface samples')
    state['phase'] = 'complete'
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#mesh-toolbar')).to_be_visible()
    expect(page.locator('#result-info')).to_contain_text('512px texture')
    page.locator('#wireframe').check()
    page.locator('#reset-view').click()
    with page.expect_download() as info:
        page.locator('#download').click()
    assert Path(info.value.path()).read_bytes().startswith(b'glTF')
    page.locator('#output_type').select_option('splat')
    expect(page.locator('#target_faces')).to_be_disabled()
    page.locator('#generate').click()
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#viewer canvas')).to_have_count(1)
    expect(page.locator('#mesh-toolbar')).to_be_hidden()
    expect(page.locator('#download')).to_contain_text('.ply')


def test_mesh_cancel_and_missing_backend(browser_page):
    page, state = browser_page
    page.locator('#output_type').select_option('mesh')
    upload(page)
    state['phase'] = 'extract'
    page.locator('#generate').click()
    expect(page.locator('#cancel')).to_be_enabled()
    page.locator('#cancel').click()
    expect(page.locator('#busy')).to_be_hidden()
    expect(page.locator('#result-info')).to_have_text('Generation cancelled.')
    expect(page.locator('#generate')).to_be_enabled()
    expect(page.locator('#cancel')).to_be_hidden()
    state['mesh_ready'] = False
    page.reload()
    page.locator('#output_type').select_option('mesh')
    upload(page)
    expect(page.locator('#setup')).to_contain_text('make setup-mesh mesh-models')
    expect(page.locator('#generate')).to_be_disabled()
