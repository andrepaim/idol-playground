"""Generate private first-party visual probes; never a population-quality corpus.

Requires installed frontend dependencies and the existing Playwright environment.
Outputs remain ignored. No owner assets, models or external image APIs are used.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
from urllib.parse import unquote, urlsplit

from PIL import Image, __version__ as pillow_version
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def drawing(family, index):
    color = ['#ae7347', '#7290b0', '#d2aa79'][index]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512"><rect width="512" height="512" fill="white"/>',
             f'<g fill="{color}" stroke="#27332c" stroke-width="4" stroke-linejoin="round" stroke-linecap="round">']
    if family == 'biped':
        spread = index * 12
        parts += [f'<path d="M215 170 L{180-spread} 290 M297 170 L{332+spread} 290" fill="none" stroke="{color}" stroke-width="30"/>',
                  f'<path d="M235 270 L{220-spread} 415 M277 270 L{292+spread} 415" fill="none" stroke="#40536b" stroke-width="35"/>',
                  '<path d="M210 165 Q256 140 302 165 L287 285 L225 285 Z"/>',
                  '<rect x="242" y="132" width="28" height="40"/>',
                  f'<ellipse cx="256" cy="105" rx="{40+index*3}" ry="45" fill="#d4aa88"/>',
                  f'<ellipse cx="{216-spread}" cy="420" rx="30" ry="13" fill="#303735"/><ellipse cx="{296+spread}" cy="420" rx="30" ry="13" fill="#303735"/>',
                  '<circle cx="243" cy="103" r="4" fill="#202020"/><circle cx="269" cy="103" r="4" fill="#202020"/>']
    elif family == 'quadruped':
        shift = index * 7
        parts += [f'<path d="M160 240 L{150-shift} 365 M195 240 L{205-shift} 365 M285 240 L{280+shift} 365 M320 240 L{335+shift} 365" fill="none" stroke="{color}" stroke-width="26"/>',
                  '<path d="M145 225 Q85 215 75 155" fill="none" stroke-width="22"/>',
                  f'<ellipse cx="235" cy="232" rx="{115+shift}" ry="57"/>',
                  '<path d="M305 215 L335 160 L365 188 L338 255 Z"/>',
                  '<ellipse cx="363" cy="159" rx="42" ry="39"/><ellipse cx="401" cy="173" rx="30" ry="21"/>',
                  f'<path d="M338 145 L{326-shift} 100 L362 128 Z"/>',
                  '<circle cx="378" cy="152" r="5" fill="#202020"/><ellipse cx="424" cy="168" rx="8" ry="10" fill="#202020"/>']
        for x in (150-shift, 205-shift, 280+shift, 335+shift):
            parts.append(f'<ellipse cx="{x+5}" cy="367" rx="22" ry="12"/>')
    elif family == 'swimmer':
        parts += ['<path d="M135 250 L55 165 L68 250 L55 335 Z"/>',
                  '<path d="M220 207 L245 135 L285 218 Z"/>',
                  f'<ellipse cx="255" cy="250" rx="{145+index*7}" ry="65"/>',
                  '<path d="M290 255 L245 335 L230 275 Z"/>',
                  '<circle cx="365" cy="232" r="7" fill="#202020"/><path d="M374 270 L395 263" fill="none"/>']
    else:
        raise ValueError('Unknown fixture family')
    return ''.join(parts) + '</g></svg>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True, help='New private .local subdirectory; never overwritten')
    args = parser.parse_args()
    if not re.fullmatch('[a-zA-Z0-9_-]+', args.name):
        raise SystemExit('Use a simple directory name.')
    output = ROOT / '.local' / args.name
    output.parent.mkdir(exist_ok=True)
    output.mkdir()  # refuse overwriting a previous run, even a partial one
    three = ROOT / 'node_modules' / 'three'
    if not (three / 'build' / 'three.module.js').is_file():
        raise SystemExit('Run npm ci first; this script never installs dependencies.')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == '/':
                data = b'<html><body><script type="importmap">{"imports":{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}</script><script type="module" src="/fixtures.js"></script></body></html>'
                kind = 'text/html'
            else:
                target = Path(__file__).with_name('fixtures.js') if path == '/fixtures.js' else (three / path.removeprefix('/three/')).resolve()
                if path != '/fixtures.js' and (not path.startswith('/three/') or not target.is_relative_to(three.resolve())):
                    self.send_error(404)
                    return
                if not target.is_file():
                    self.send_error(404)
                    return
                data = target.read_bytes()
                kind = 'application/javascript'
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assets = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=['--no-sandbox', '--enable-unsafe-swiftshader', '--use-angle=swiftshader'])
            try:
                render = browser.new_page(viewport={'width':512, 'height':512})
                sketch = browser.new_page(viewport={'width':512, 'height':512})
                render.goto(f'http://127.0.0.1:{server.server_port}')
                render.wait_for_function('typeof window.makeFixture === "function"')
                for family in ('biped', 'quadruped', 'swimmer'):
                    for index in range(3):
                        for style in ('drawing', 'render'):
                            identifier = f'{family}-{style}-{index+1:02}'
                            metadata = {'id':identifier, 'family':family, 'style':style, 'specimen':index+1,
                                        'split':'held-out-probe' if index == 2 else 'development-probe',
                                        'scope':'Procedural regression probe only; not independent population acceptance.'}
                            if style == 'drawing':
                                svg = drawing(family, index)
                                (output / f'{identifier}.svg').write_text(svg)
                                sketch.set_content('<style>body{margin:0}</style>' + svg)
                                sketch.locator('svg').screenshot(path=str(output / f'{identifier}.png'))
                            else:
                                result = render.evaluate('([family,index])=>window.makeFixture(family,index)', [family,index])
                                render.locator('canvas').screenshot(path=str(output / f'{identifier}.png'))
                                geometry = bytes(result.pop('glb'))
                                (output / f'{identifier}.glb').write_bytes(geometry)
                                metadata.update(source_glb_sha256=sha256(geometry).hexdigest(), reference=result,
                                                reference_scope='Authored static geometry/anchors, not anatomical ground truth or a validated rig.')
                            image = output / f'{identifier}.png'
                            with Image.open(image) as decoded:
                                if decoded.size != (512,512):
                                    raise RuntimeError('Unexpected fixture dimensions.')
                            metadata.update(image=image.name, sha256=sha256(image.read_bytes()).hexdigest(), width=512, height=512)
                            assets.append(metadata)
                browser_version = browser.version
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    receipt = {'generated_at':datetime.now(timezone.utc).isoformat(), 'base_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
               'dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
               'python':sys.version.split()[0], 'pillow':pillow_version, 'three':json.loads((three/'package.json').read_text())['version'],
               'generator_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
               'renderer_source_sha256':sha256(Path(__file__).with_name('fixtures.js').read_bytes()).hexdigest(),
               'browser':browser_version, 'rights':'First-party procedural fixtures; no third-party visual assets; local evaluation only, no redistribution grant asserted.',
               'complete_roadmap_corpus':False, 'limitations':['Shared procedural generator; held-out probes do not replace independently sourced subjects.', 'No real photographs or independently authored rigs in this set.'], 'assets':assets}
    (output / 'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    cards = ''.join(f'<div><p>{a["id"]}</p><img width="240" height="240" src="{a["image"]}"></div>' for a in assets)
    (output / 'review.html').write_text('<html><body style="display:grid;grid-template-columns:repeat(3,250px);font:14px sans-serif">'+cards+'</body></html>')
    print(json.dumps({'assets':len(assets),'manifest':str(output.relative_to(ROOT) / 'manifest.json'),'roadmap_corpus_complete':False}))


if __name__ == '__main__':
    main()
