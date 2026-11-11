// Deterministic first-party research fixtures, never imported by the app.
import * as THREE from '/three/build/three.module.js';
import { GLTFExporter } from '/three/examples/jsm/exporters/GLTFExporter.js';

const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(1); renderer.setSize(512,512);
document.body.style.margin = '0'; document.body.append(renderer.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color('white');
scene.add(new THREE.HemisphereLight(0xffffff,0x8b8b8b,2));
const light = new THREE.DirectionalLight(0xffffff,2); light.position.set(3,5,4); scene.add(light);
const camera = new THREE.PerspectiveCamera(35,1,.01,100);
let actor;
function sphere(group, position, size, color) {
  const object = new THREE.Mesh(new THREE.SphereGeometry(1,20,16), new THREE.MeshStandardMaterial({color,roughness:.8}));
  object.position.set(...position); object.scale.set(...size); group.add(object); return object;
}
function link(group, a, b, radius, color) {
  const start = new THREE.Vector3(...a), end = new THREE.Vector3(...b);
  const object = new THREE.Mesh(new THREE.CylinderGeometry(radius*.85,radius,start.distanceTo(end),12),new THREE.MeshStandardMaterial({color,roughness:.8}));
  object.position.copy(start).add(end).multiplyScalar(.5);
  object.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),end.sub(start).normalize());group.add(object);
  sphere(group,a,[radius,radius,radius],color);sphere(group,b,[radius*.85,radius*.85,radius*.85],color);
}
function fin(group, coordinates, color) {
  const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position',new THREE.Float32BufferAttribute(coordinates.flat(),3));geometry.computeVertexNormals();
  group.add(new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color,side:THREE.DoubleSide,roughness:.8})));
}
window.makeFixture = async (family,index) => {
  if (!['biped','quadruped','swimmer'].includes(family) || !Number.isInteger(index) || index<0 || index>2) throw new Error('Unsupported fixture specification.');
  if (actor) {
    scene.remove(actor);
    actor.traverse(node=>{node.geometry?.dispose();node.material?.dispose();});
  }
  actor = new THREE.Group();
  const coat = [0xb47a4d,0x677e99,0xd6b58c][index];
  const joints = {};
  if (family === 'quadruped') {
    const height = 1+index*.12, length = 1+index*.1;
    sphere(actor,[0,height,0],[length,.42,.38],coat);
    link(actor,[.6,height,0],[1.05,height+.5,0],.28,coat);
    sphere(actor,[1.1,height+.5,0],[.4,.4,.32],coat);
    sphere(actor,[1.45,height+.45,0],[.28,.2,.24],coat);
    for (const side of [-1,1]) {
      sphere(actor,[1.12,height+.8,side*.25],[.13,.25+index*.03,.1],coat);
      sphere(actor,[1.34,height+.56,side*.29],[.045,.045,.03],0x202020);
      for (const x of [-.7,.65]) {
        const label=(x<0?'hind':'fore')+(side<0?'_left':'_right');
        const hip=[x,height,side*.27], knee=[x+(x<0?.13:-.06),.5,side*.29], foot=[x+.1,.12,side*.3];
        link(actor,hip,knee,.14,coat);link(actor,knee,foot,.11,coat);
        sphere(actor,[foot[0]+.06,.12,foot[2]],[.21,.12,.16],coat);
        joints[label]={root:hip,mid:knee,contact:foot};
      }
    }
    link(actor,[-.85,height+.1,0],[-1.3,height+.3,0],.13,coat);
    link(actor,[-1.3,height+.3,0],[-1.5,height+.75,.08],.09,coat);
  } else if (family === 'biped') {
    const spread=.4+index*.06;
    sphere(actor,[0,1.25,0],[spread,.6,.24],coat);
    sphere(actor,[0,.75,0],[.31,.24,.23],0x404e65);
    link(actor,[0,1.65,0],[0,1.95,0],.12,coat);
    sphere(actor,[0,2.08,0],[.25+index*.025,.3,.24],0xd4aa88);
    for (const side of [-1,1]) {
      const shoulder=[side*spread,1.6,0], elbow=[side*(spread+.2),1.15,0], hand=[side*(spread+.25),.8,.05];
      link(actor,shoulder,elbow,.11,coat);link(actor,elbow,hand,.09,0xd4aa88);
      const hip=[side*.18,.75,0], knee=[side*.2,.42,0], foot=[side*.23,.1,.06];
      link(actor,hip,knee,.13,0x404e65);link(actor,knee,foot,.11,0x404e65);
      sphere(actor,[side*.23,.09,.14],[.15,.09,.24],0x252c35);
      joints[side<0?'left':'right']={shoulder,elbow,hand,hip,knee,foot};
      sphere(actor,[side*.09,2.12,.225],[.025,.025,.025],0x202020);
    }
  } else {
    sphere(actor,[0,1,0],[1.1,.42+index*.04,.3],coat);
    sphere(actor,[.9,1,0],[.4,.32,.27],coat);
    link(actor,[-.9,1,0],[-1.45,1,0],.14,coat);
    fin(actor,[[-1.4,1,0],[-2,1.6,0],[-1.8,1,0]],coat);
    fin(actor,[[-1.4,1,0],[-1.8,1,0],[-2,.4,0]],coat);
    fin(actor,[[.3,1.2,0],[-.1,1.95,0],[-.45,1.2,0]],coat);
    for (const side of [-1,1]) {
      fin(actor,[[.65,.9,side*.22],[.1,.45,side*.8],[-.1,.85,side*.25]],coat);
      sphere(actor,[1.03,1.1,side*.24],[.04,.04,.025],0x202020);
    }
    joints.axial=[[1.1,1,0],[.4,1,0],[-.4,1,0],[-1.2,1,0],[-1.8,1,0]];
  }
  scene.add(actor); actor.updateMatrixWorld(true);
  const bounds=new THREE.Box3().setFromObject(actor), center=bounds.getCenter(new THREE.Vector3());
  const size=bounds.getSize(new THREE.Vector3()), distance=Math.max(size.x,size.y,size.z)*2;
  camera.position.copy(center).add(new THREE.Vector3(3,1.6,6).normalize().multiplyScalar(distance));camera.lookAt(center);camera.updateMatrixWorld();
  renderer.render(scene,camera);
  const binary = await new GLTFExporter().parseAsync(actor,{binary:true});
  const gl=renderer.getContext(), extension=gl.getExtension('WEBGL_debug_renderer_info');
  return {glb:Array.from(new Uint8Array(binary)),joints,bounds:{min:bounds.min.toArray(),max:bounds.max.toArray()},renderer:extension?gl.getParameter(extension.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER)};
};
