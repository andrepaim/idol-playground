"""Browser review and gameplay check for a vertical-slice character (issue #72).

    python experiments/vertical_slice/capture_review.py RUN_DIR [--hardware]

From the repository root (which must contain node_modules): renders fixed review frames with
review.html into RUN_DIR/review/, then assembles RUN_DIR/sample/ from the unchanged runtime modules
(web/playable-viewer.js, web/character-controller.js) and drives it with the keyboard. Results go to
RUN_DIR/browser-receipt.json. Default rendering is SwiftShader (functional evidence only).
"""
import argparse
import functools
import hashlib
import http.server
import json
import shutil
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('run', type=Path)
parser.add_argument('--hardware', action='store_true', help='use the default GPU path instead of SwiftShader')
args = parser.parse_args()
run = args.run.resolve()
receipt = {'run': str(run.relative_to(root)), 'errors': []}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(directory):
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def build_sample():
    sample = run / 'sample'
    if sample.exists():
        shutil.rmtree(sample)
    sample.mkdir()
    for name in ('playable-viewer.js', 'character-controller.js'):
        shutil.copy(root / 'web' / name, sample / name)
    html = (root / 'web/sample-template/index.html').read_text().replace('Playable canine sample', 'Vertical slice (experimental)')
    (sample / 'index.html').write_text(html)
    script = (root / 'web/sample-template/sample.js').read_text()
    gate = "manifest.profile !== 'canine-34-v1'"
    assert gate in script, 'sample template changed; update the experiment profile gate'
    (sample / 'sample.js').write_text(script.replace(gate, "manifest.profile !== 'quadruped-fox24-experimental'"))
    shutil.copy(run / 'character.glb', sample / 'character.glb')
    (sample / 'node_modules').symlink_to(root / 'node_modules')
    motion = json.loads((run / 'receipt.json').read_text())['motion']
    digest = hashlib.sha256((sample / 'character.glb').read_bytes()).hexdigest()
    (sample / 'character.json').write_text(json.dumps({
        'schema_version': 1, 'profile': 'quadruped-fox24-experimental',
        'geometry': {'file': 'character.glb', 'sha256': digest},
        'motion': {'clip': 'Walk_inplace', 'mode': 'inplace', 'stride': motion['stride_model_units']},
        'limitations': 'Feasibility spike #72; not accepted for any tier.'}, indent=2))
    return sample


def launch(p):
    flags = ['--no-sandbox'] + ([] if args.hardware else ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'])
    return p.chromium.launch(args=flags)


with sync_playwright() as p:
    browser = launch(p)
    receipt['browser'] = browser.version
    server = serve(root)
    page = browser.new_page(viewport={'width': 480, 'height': 360})
    page.on('pageerror', lambda e: receipt['errors'].append(str(e)))
    page.goto(f'http://127.0.0.1:{server.server_port}/experiments/vertical_slice/review.html'
              f'?model=/{(run / "character.glb").relative_to(root)}')
    page.wait_for_selector('body[data-ready="1"]', timeout=60000)
    renderer = page.evaluate("""() => { const gl = document.querySelector('canvas').getContext('webgl2');
        const ext = gl.getExtension('WEBGL_debug_renderer_info');
        return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); }""")
    receipt['review_renderer'] = renderer
    review = run / 'review'
    review.mkdir(exist_ok=True)
    phases = [0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875]
    views = page.evaluate('review.views')
    tiles = {}
    for view in views:
        for phase in phases:
            page.evaluate(f'review.show({json.dumps(view)}, {phase})')
            path = review / f'{view}-{int(phase * 1000):03d}.png'
            page.locator('canvas').screenshot(path=str(path))
            tiles[(view, phase)] = path
    for view in ('right', 'front'):
        page.evaluate(f'review.show({json.dumps(view)}, 0, true, 0.15)')
        page.locator('canvas').screenshot(path=str(review / f'skeleton-{view}.png'))
    sheet = Image.new('RGB', (240 * len(phases), 180 * len(views) + 20), 'white')
    draw = ImageDraw.Draw(sheet)
    for column, phase in enumerate(phases):
        draw.text((240 * column + 4, 4), f'phase {phase:.3f}', fill='black')
    for row, view in enumerate(views):
        for column, phase in enumerate(phases):
            tile = Image.open(tiles[(view, phase)]).resize((240, 180))
            sheet.paste(tile, (240 * column, 20 + 180 * row))
        draw.text((4, 24 + 180 * row), view, fill='black')
    sheet.save(review / 'contact-sheet.png')
    page.close()
    server.shutdown()

    sample = build_sample()
    server = serve(sample)
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    page.on('pageerror', lambda e: receipt['errors'].append(str(e)))
    requests = []
    page.on('request', lambda r: requests.append(r.url))
    page.goto(f'http://127.0.0.1:{server.server_port}/')
    page.wait_for_function("document.getElementById('status').textContent.startsWith('Ready') || "
                           "document.getElementById('status').textContent.startsWith('Unable')", timeout=60000)
    receipt['sample_status'] = page.text_content('#status')
    view = page.locator('#play-view')
    canvas = page.locator('#play-view canvas')
    page.screenshot(path=str(run / 'play-standing.png'))
    canvas.click()
    track = []
    page.keyboard.down('KeyW')
    started = time.time()
    while time.time() - started < 6:
        time.sleep(0.25)
        track.append((round(time.time() - started, 2), float(view.get_attribute('data-x')),
                      float(view.get_attribute('data-z')), page.text_content('#play-motion') if page.locator('#play-motion').count() else None))
        if abs(track[-1][0] - 1.5) < 0.13:
            page.screenshot(path=str(run / 'play-walking.png'))
    page.keyboard.up('KeyW')
    time.sleep(0.5)
    still = (float(view.get_attribute('data-x')), float(view.get_attribute('data-z')))
    time.sleep(0.5)
    receipt['gameplay'] = {
        'track_seconds_x_z': track,
        'moved_distance': ((track[-1][1]) ** 2 + (track[-1][2]) ** 2) ** 0.5,
        'blocked_at_end': abs(track[-1][1] - track[-3][1]) + abs(track[-1][2] - track[-3][2]) < 1e-3,
        'stops_after_release': (float(view.get_attribute('data-x')), float(view.get_attribute('data-z'))) == still,
        'external_requests': [u for u in requests if not u.startswith(f'http://127.0.0.1:{server.server_port}/')
                              and not u.startswith('blob:')],
    }
    page.click('#reset')
    time.sleep(0.3)
    receipt['gameplay']['reset_to_origin'] = (view.get_attribute('data-x'), view.get_attribute('data-z')) == ('0', '0')
    # From the reset camera, S+D heads mostly +X into the box obstacle at x 3..4, z -1..1 (radius 1).
    canvas.click()
    page.keyboard.down('KeyS')
    page.keyboard.down('KeyD')
    collision = []
    started = time.time()
    while time.time() - started < 8:
        time.sleep(0.25)
        collision.append((round(time.time() - started, 2), float(view.get_attribute('data-x')),
                          float(view.get_attribute('data-z'))))
    page.screenshot(path=str(run / 'play-blocked.png'))
    page.keyboard.up('KeyS')
    page.keyboard.up('KeyD')
    receipt['gameplay']['collision_track'] = collision
    receipt['gameplay']['max_x_reached'] = max(x for _, x, _ in collision)
    receipt['gameplay']['obstacle_face_minus_radius'] = 2.0
    browser.close()
    server.shutdown()
(run / 'browser-receipt.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps({k: v for k, v in receipt.items() if k != 'gameplay'}, indent=1))
print(json.dumps({k: v for k, v in receipt['gameplay'].items() if k != 'track_seconds_x_z'}))
