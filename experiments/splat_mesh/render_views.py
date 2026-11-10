"""Render a saved PLY locally with the app's unchanged Gaussian renderer, no inference/API mutation."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.splat_mesh.geometry import cv_extrinsic


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--splat',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    manifest={'source_sha256':hashlib.sha256(args.splat.read_bytes()).hexdigest(),
              'renderer':'@mkkellogg/gaussian-splats-3d 0.4.7 / Three 0.170.0',
              'rendering':'Chromium software WebGL (SwiftShader); not CUDA inference', 'pairs':[], 'heldout':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--no-sandbox','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':512,'height':512})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        def route(request):
            from urllib.parse import urlparse
            path=urlparse(request.request.url).path
            if path=='/':
                request.fulfill(content_type='text/html',body='<div id="root" style="width:512px;height:512px"></div><script type="importmap">{"imports":{"three":"/node_modules/three/build/three.module.js"}}</script><script type="module" src="/render.js"></script>')
            elif path=='/source.ply':request.fulfill(path=str(args.splat.resolve()),content_type='application/octet-stream')
            elif path=='/render.js':request.fulfill(path=str(Path(__file__).with_name('render.js')),content_type='text/javascript')
            elif path.startswith('/node_modules/'):
                file=(ROOT/path.lstrip('/')).resolve();node=(ROOT/'node_modules').resolve()
                if not file.is_relative_to(node) or not file.is_file():request.abort();return
                request.fulfill(path=str(file),content_type='text/javascript')
            else:request.abort()
        page.route('**/*',route)
        page.goto(args.base_url,wait_until='networkidle')
        page.wait_for_function('window.captureReady===true',timeout=180000)
        def capture(az,el,eye,name):
            item=page.evaluate('([az,el,eye])=>window.capture(az,el,eye)',[az,el,eye])
            data=base64.b64decode(item.pop('png').split(',',1)[1]);(args.output/name).write_bytes(data)
            item['file']=name;item['extrinsic']=cv_extrinsic(item['matrix'])
            return item
        for el in [-20,15,50]:
            for az in range(0,360,30):
                index=len(manifest['pairs']);pair={}
                for eye in ['left','right']:pair[eye]=capture(az,el,eye,f'{index:03}-{eye}.png')
                manifest['pairs'].append(pair)
                (args.output/'views.json').write_text(json.dumps(manifest,indent=2))
                print('STEREO VIEW',index+1,'of 36',round(time.monotonic()-started,1),'s',flush=True)
        for index in range(8):manifest['heldout'].append(capture(7.5+45*index,15,'left',f'heldout-{index:02}.png'))
        assert not errors,errors
        browser.close()
    manifest['render_seconds']=round(time.monotonic()-started,2)
    (args.output/'views.json').write_text(json.dumps(manifest,indent=2))
    print('Rendered calibrated views and held-out references',flush=True)


if __name__=='__main__':main()
