"""Prepare a private local review artifact for the existing localhost static output server."""
import argparse
import html
import json
from pathlib import Path
import shutil


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--web-dist',type=Path,required=True)
    args=parser.parse_args()
    bundle=next(args.web_dist.glob('assets/mesh-viewer-*.js'),None)
    if bundle is None:raise RuntimeError('Build the existing app before preparing a local review')
    report=json.loads((args.result/'report.json').read_text())
    metrics=json.loads((args.result/'evaluation/silhouettes.json').read_text())
    args.output.mkdir(parents=True,exist_ok=False)
    shutil.copy2(args.result/'mesh.glb',args.output/'mesh.glb')
    shutil.copy2(args.result/'inspection/comparison.png',args.output/'comparison.png')
    (args.output/'report.json').write_text(json.dumps({'surface':report,'heldout_silhouettes':metrics},indent=2))
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Splat-derived mesh experiment</title>
<style>body{margin:0;background:#101713;color:#e7eee3;font:16px/1.6 system-ui}main{max-width:1100px;margin:auto;padding:32px 20px}h1{font-size:32px;line-height:1.2}a{color:#c8e89e}#viewer{height:560px;background:#161e18;border:1px solid #3b4a3b;border-radius:12px}nav{display:flex;gap:22px;flex-wrap:wrap;margin:16px 0}button{background:#26351f;color:#dcebd0;border:1px solid #526647;padding:7px 13px;border-radius:5px}img{width:100%;height:auto;background:#eeeeea;border-radius:10px}small{color:#b6c1b1}#error{color:#ffc6ad}</style>
<main><small>LOCAL FIDELITY EXPERIMENT · UNRIGGED</small><h1>Mesh reconstructed from the Idol splat</h1>
<p>The saved splat supplied calibrated stereo views. Learned stereo depth was fused into this mesh; the original photo was not reconstructed by TripoSR.</p>
<p><strong>METRIC silhouette overlap</strong> across eight withheld camera angles. This measures agreement with the splat's outline, not anatomical accuracy.</p>
<div id="viewer"></div><p id="error" hidden></p><nav><button id="reset">Reset view</button><label><input type="checkbox" id="wireframe"> Wireframe</label><a href="mesh.glb" download="splat-derived-mesh.glb">Download GLB</a><a href="report.json">Measurements</a></nav>
<p><small>TRIANGLES triangles · vertex colors · no UV texture map or skeleton. Small detached fragments were excluded; the raw reconstruction is retained locally. Fine details remain rough and the mesh has holes. Review topology before animation.</small></p>
<h2>Same cameras, same object</h2><p>Left: Idol splat. Right: the reconstructed mesh. These camera angles were withheld from fusion.</p><img src="comparison.png" alt="Four camera-matched comparisons of the Idol splat and reconstructed mesh">
<script type="module">import {loadMeshViewer} from 'BUNDLE';try{const viewer=await loadMeshViewer(document.querySelector('#viewer'),'./mesh.glb');document.querySelector('#wireframe').onchange=e=>viewer.wireframe(e.target.checked);document.querySelector('#reset').onclick=()=>viewer.reset();}catch(error){document.querySelector('#error').hidden=false;document.querySelector('#error').textContent=error.message;}</script></main></html>'''
    page=page.replace('METRIC',f'{metrics["mean_iou"]*100:.1f}%').replace('TRIANGLES',f'{report["triangles"]:,}').replace('BUNDLE',html.escape('/assets/'+bundle.name))
    (args.output/'review.html').write_text(page)
    print('Local review prepared at',args.output/'review.html')


if __name__=='__main__':main()
