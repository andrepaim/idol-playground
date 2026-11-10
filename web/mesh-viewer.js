import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export async function loadMeshViewer(container, url, options = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, container.clientWidth / container.clientHeight, .01, 100);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x626c61, 2));
  const key = new THREE.DirectionalLight(0xffffff, 2.5);
  key.position.set(2, 3, 4);
  scene.add(key);
  let object, frame, observer, skeleton, mixer, action, grid, marker, selectedBone, disposed = false;
  let following = true, accumulated = 0, gridStep = 1;
  const lastPosition = new THREE.Vector3();
  const currentPosition = new THREE.Vector3();
  let rootBone;
  const clock = new THREE.Clock();
  const initial = new THREE.Vector3();
  const dispose = () => {
    disposed = true;
    cancelAnimationFrame(frame);
    observer?.disconnect();
    controls.dispose();
    mixer?.stopAllAction();
    if (mixer && object) mixer.uncacheRoot(object);
    grid?.geometry.dispose();
    grid?.material.dispose();
    marker?.geometry.dispose(); marker?.material.dispose();
    skeleton?.geometry.dispose();
    skeleton?.material.dispose();
    const geometries = new Set(), materials = new Set(), textures = new Set();
    object?.traverse((node) => {
      if (node.geometry) geometries.add(node.geometry);
      const list = Array.isArray(node.material) ? node.material : [node.material];
      for (const material of list.filter(Boolean)) materials.add(material);
    });
    for (const material of materials) {
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
      material.dispose();
    }
    for (const texture of textures) { texture.image?.close?.(); texture.dispose(); }
    for (const geometry of geometries) geometry.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    renderer.domElement.remove();
  };
  try {
    const gltf = await new GLTFLoader().loadAsync(url);
    object = gltf.scene;
    if (options.walking && gltf.animations.length) {
      mixer = new THREE.AnimationMixer(object);
      action = mixer.clipAction(gltf.animations[0]); action.play(); mixer.update(0);
      object.updateMatrixWorld(true);
      object.traverse((node) => { if (node.isSkinnedMesh) node.frustumCulled = false; });
    }
    const box = new THREE.Box3().setFromObject(object);
    if (box.isEmpty()) throw new Error('The GLB contains no visible mesh.');
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    object.position.sub(center);
    scene.add(object);
    rootBone = object.getObjectByName('bone_0');
    marker = new THREE.Mesh(new THREE.SphereGeometry(Math.max(...size.toArray()) * .018, 12, 8), new THREE.MeshBasicMaterial({color:0xff8a00,depthTest:false}));
    marker.visible = false; marker.renderOrder = 20; scene.add(marker);
    if (options.walking) {
      grid = new THREE.GridHelper(Math.max(...size.toArray()) * 3, 24, 0x688066, 0xbac6b3);
      grid.position.y = options.ground - center.y;
      gridStep = Math.max(...size.toArray()) * 3 / 24;
      scene.add(grid);
    }
    if (object.getObjectByProperty('isSkinnedMesh', true)) {
      skeleton = new THREE.SkeletonHelper(object);
      skeleton.visible = false;
      skeleton.material.depthTest = false;
      skeleton.renderOrder = 10;
      scene.add(skeleton);
    }
    if (gltf.animations.length && !mixer) {
      mixer = new THREE.AnimationMixer(object);
      action = mixer.clipAction(gltf.animations.find((clip) => clip.name.includes('Diagnostic')) || gltf.animations[0]);
    }
    if (options.walking && mixer) {
      mixer.addEventListener('loop', (event) => {
        const travel = (options.stride || 0) * event.loopDelta;
        accumulated += travel; object.position.x += travel;
      });
    }

    const distance = Math.max(size.y, size.x / camera.aspect, size.z) / (2 * Math.tan(THREE.MathUtils.degToRad(20))) * 1.4;
    initial.set(distance * .65, distance * .25, distance);
    camera.position.copy(initial);
    camera.near = Math.max(distance / 100, .001);
    camera.far = distance * 100;
    camera.updateProjectionMatrix();
    controls.target.set(0, 0, 0);
    controls.update();
    observer = new ResizeObserver(() => {
      if (disposed) return;
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    });
    observer.observe(container);
    object.updateMatrixWorld(true);
    rootBone?.getWorldPosition(lastPosition);
    const followTravel = () => {
      if (!rootBone) return;
      object.updateMatrixWorld(true); rootBone.getWorldPosition(currentPosition);
      const delta = currentPosition.clone().sub(lastPosition); delta.y = 0;
      if (options.walking && following) { camera.position.add(delta); controls.target.add(delta); }
      if (grid) grid.position.x = Math.floor(currentPosition.x / gridStep) * gridStep;
      lastPosition.copy(currentPosition);
    };
    const resetTravel = () => {
      object.position.x -= accumulated; accumulated = 0;
    };
    const animate = () => {
      if (disposed) return;
      mixer?.update(Math.min(clock.getDelta(), .1));
      followTravel();
      if (selectedBone) { selectedBone.getWorldPosition(marker.position); marker.visible = true; }
      if (options.walking && action) options.onTime?.(action.time, action.getClip().duration);
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };
    animate();
    return {
      dispose,
      state() {
        object.updateMatrixWorld(true);
        return {playing:Boolean(action?.isRunning()),time:action?.time,duration:action?.getClip().duration,travel:accumulated,
          root:rootBone?.getWorldPosition(new THREE.Vector3()).toArray(),floor:grid?.position.y,
          camera:camera.position.toArray(),target:controls.target.toArray()};
      },
      play(enabled) { if (action) { action.play(); action.paused = !enabled; } },
      restart() { if (action) { resetTravel(); action.reset().play(); mixer.update(0); followTravel(); } },
      rest() { if (action) { resetTravel(); action.stop(); mixer.update(0); followTravel(); } },
      seek(time) { if (action) { resetTravel(); action.play(); action.paused = true; action.time = Math.min(time,action.getClip().duration - 1e-6); mixer.update(0); followTravel(); } },
      speed(value) { if (mixer) mixer.timeScale = value; },
      floor(enabled) { if (grid) grid.visible = enabled; },
      follow(enabled) { following = enabled; },
      highlight(name) { selectedBone = object.getObjectByName(name); marker.visible = Boolean(selectedBone); },
      hasSkeleton: Boolean(skeleton),
      hasAnimation: Boolean(action),
      orbit: { camera, controls, render() {} },
      skeleton(enabled) { if (skeleton) skeleton.visible = enabled; },
      diagnostic(enabled) { if (action) { if (enabled) action.reset().play(); else action.stop(); } },
      reset() {
        const offset = options.walking && rootBone ? lastPosition.clone() : new THREE.Vector3();
        offset.y = 0;
        camera.position.copy(initial).add(offset); controls.target.copy(offset); controls.update();
      },
      wireframe(enabled) {
        object.traverse((node) => {
          for (const material of (Array.isArray(node.material) ? node.material : [node.material]).filter(Boolean)) {
            material.wireframe = enabled;
            material.needsUpdate = true;
          }
        });
      },
    };
  } catch (error) {
    dispose();
    throw error;
  }
}
