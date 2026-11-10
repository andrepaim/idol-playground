/* global document, window */
import * as THREE from '/node_modules/three/build/three.module.js';
import { Viewer } from '/node_modules/@mkkellogg/gaussian-splats-3d/build/gaussian-splats-3d.module.js';

const size = 512, fov = 42, radius = 1.5, baseline = .075;
const root = document.getElementById('root');
const renderer = new THREE.WebGLRenderer({alpha:true, antialias:false, preserveDrawingBuffer:true});
renderer.setSize(size, size);
renderer.setPixelRatio(1);
renderer.setClearColor(0x000000,0);
root.appendChild(renderer.domElement);
const camera = new THREE.PerspectiveCamera(fov,1,.01,10);
camera.up.set(0,-1,0);
const viewer = new Viewer({rootElement:root, renderer, camera, selfDrivenMode:false, useBuiltInControls:false,
  sharedMemoryForWorkers:false, gpuAcceleratedSort:false, sphericalHarmonicsDegree:0});
await viewer.addSplatScene('/source.ply',{splatAlphaRemovalThreshold:5,showLoadingUI:false,progressiveLoad:false});
window.capture = async (azimuth,elevation,eye='left') => {
  if(viewer.sortPromise) await viewer.sortPromise;
  const az=THREE.MathUtils.degToRad(azimuth),el=THREE.MathUtils.degToRad(elevation);
  const target=new THREE.Vector3(0,-.03,0);
  camera.position.set(radius*Math.sin(az)*Math.cos(el),-radius*Math.sin(el)-.03,radius*Math.cos(az)*Math.cos(el));
  camera.lookAt(target);
  camera.updateMatrixWorld(true);
  if(eye==='right'){
    const right=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,0);
    camera.position.addScaledVector(right,baseline);
    camera.updateMatrixWorld(true);
  }
  camera.updateProjectionMatrix();
  await viewer.runSplatSort(true,true);
  if(viewer.sortPromise) await viewer.sortPromise;
  viewer.updateForRendererSizeChanges();viewer.updateSplatMesh();
  viewer.render();renderer.getContext().finish();
  return {png:renderer.domElement.toDataURL('image/png'),matrix:camera.matrixWorld.toArray(),
    size,fov,radius,baseline,focal:size/(2*Math.tan(THREE.MathUtils.degToRad(fov/2))),azimuth,elevation,eye};
};
window.captureReady=true;
