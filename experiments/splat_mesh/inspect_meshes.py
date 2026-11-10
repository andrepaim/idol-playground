"""Render actual exported meshes from the exact held-out cameras for private visual review."""
import argparse
import base64
import json
from pathlib import Path
import time
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--views',type=Path,required=True)
    parser.add_argument('--mesh',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((args.views/'views.json').read_text())
    script='''
import * as THREE from '/node_modules/three/build/three.module.js';
import { GLTFLoader } from '/node_modules/three/examples/jsm/loaders/GLTFLoader.js';
const renderer=new THREE.WebGLRenderer({alpha:true,antialias:false,preserveDrawingBuffer:true});
renderer.setSize(512,512);renderer.setClearColor(0,0);document.body.appendChild(renderer.domElement);
const scene=new THREE.Scene();const camera=new THREE.PerspectiveCamera(42,1,.01,10);
const object=(await new GLTFLoader().loadAsync('/mesh.glb')).scene;
object.traverse(node=>{
 if(!node.isMesh)return;
 const colors=node.geometry.getAttribute('color');
 if(colors && !node.material.isMeshBasicMaterial){
   const linear=[];const c=new THREE.Color();
   for(let i=0;i<colors.count;i++){c.setRGB(colors.getX(i),colors.getY(i),colors.getZ(i),THREE.SRGBColorSpace);linear.push(c.r,c.g,c.b);}
   node.geometry.setAttribute('color',new THREE.Float32BufferAttribute(linear,3));
 }
 node.material=new THREE.MeshBasicMaterial({vertexColors:Boolean(colors),map:node.material.map||null,side:THREE.DoubleSide});
});scene.add(object);
window.renderMesh=(pose)=>{
 camera.matrix.fromArray(pose.matrix);camera.matrix.decompose(camera.position,camera.quaternion,camera.scale);
 camera.updateMatrixWorld(true);camera.fov=pose.fov;camera.updateProjectionMatrix();
 renderer.render(scene,camera);renderer.getContext().finish();return renderer.domElement.toDataURL('image/png');
};window.ready=true;
'''
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--no-sandbox','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':512,'height':512})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        def route(request):
            from urllib.parse import urlparse
            path=urlparse(request.request.url).path
            if path=='/':request.fulfill(content_type='text/html',body='<script type="importmap">{"imports":{"three":"/node_modules/three/build/three.module.js"}}</script><script type="module" src="/inspect.js"></script>')
            elif path=='/inspect.js':request.fulfill(content_type='text/javascript',body=script)
            elif path=='/mesh.glb':request.fulfill(path=str(args.mesh.resolve()),content_type='model/gltf-binary')
            elif path.startswith('/node_modules/'):
                file=(ROOT/path.lstrip('/')).resolve()
                if not file.is_relative_to((ROOT/'node_modules').resolve()) or not file.is_file():request.abort();return
                request.fulfill(path=str(file),content_type='text/javascript')
            else:request.abort()
        page.route('**/*',route)
        page.goto('http://127.0.0.1:8000',wait_until='networkidle');page.wait_for_function('window.ready',timeout=60000)
        gl=page.evaluate("(()=>{const g=document.querySelector('canvas').getContext('webgl2');const e=g.getExtension('WEBGL_debug_renderer_info');return e?g.getParameter(e.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER);})()")
        for index,pose in enumerate(manifest['heldout']):
            encoded=page.evaluate('pose=>window.renderMesh(pose)',pose)
            (args.output/f'{index:02}.png').write_bytes(base64.b64decode(encoded.split(',',1)[1]))
        assert not errors,errors
        browser.close()
    sheet=Image.new('RGB',(1024,4*540),'#eeeeea');draw=ImageDraw.Draw(sheet)
    for row,index in enumerate([0,2,4,6]):
        for column,file in enumerate([args.views/manifest['heldout'][index]['file'],args.output/f'{index:02}.png']):
            rgba=Image.open(file).convert('RGBA');bg=Image.new('RGBA',rgba.size,'#eeeeea');bg.alpha_composite(rgba)
            sheet.paste(bg.convert('RGB'),(column*512,row*540+28))
        draw.text((10,row*540+7),f'Idol splat / {manifest["heldout"][index]["azimuth"]:.1f} degrees',fill='black')
        draw.text((522,row*540+7),'Mesh reconstructed from that splat',fill='black')
    sheet.save(args.output/'comparison.png')
    (args.output/'viewer.json').write_text(json.dumps({'renderer':gl,'heldout_views':8,'errors':errors,'time':time.time()},indent=2))
    print('Rendered actual exported mesh comparison',gl,flush=True)


if __name__=='__main__':main()
