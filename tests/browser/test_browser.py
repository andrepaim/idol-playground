"""Real Chromium acceptance against built UI; API and splats are synthetic."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import math
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
            if self.path == '/fixture.ply':
                data = splat_bytes()
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


@pytest.fixture
def browser_page(site):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=['--no-sandbox', '--enable-unsafe-swiftshader'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        state = {'phase': 'sampling', 'ready': True, 'submissions': 0}

        def api(route):
            path = route.request.url.split('/api/')[1]
            if path == 'status':
                route.fulfill(json={'ready': state['ready'], 'weights_downloaded': True})
            elif path == 'generate':
                state['submissions'] += 1
                route.fulfill(status=202, json={'id': 'fixture'})
            else:
                phase = state['phase']
                job = {'stage': phase, 'state': 'running', 'message': 'Generating synthetic fixture',
                       'step': 4, 'total_steps': 10, 'elapsed_seconds': 12,
                       'eta_seconds': 45, 'eta_basis': 'measured'}
                if phase == 'error':
                    job.update(state='error', message='Synthetic GPU failure')
                if phase == 'complete':
                    job.update(state='complete', seconds=20, settings={'num_gaussians': 128, 'seed': 42},
                               files={'object.ply': '/fixture.ply'})
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
