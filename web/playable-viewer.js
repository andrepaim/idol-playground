import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CharacterController } from './character-controller.js';

export async function loadPlayable(container, url, {stride, onMotion = () => {}}) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe6eee8);
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(1);
  const canvas = renderer.domElement;
  canvas.tabIndex = 0;
  canvas.setAttribute('aria-label', 'Character controls: WASD or arrow keys');
  container.append(canvas);
  const camera = new THREE.PerspectiveCamera(45, 1, .01, 100);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.minDistance = 2;
  controls.maxDistance = 15;
  const actor = new THREE.Group();
  scene.add(actor);
  const keys = new Set();
  const handlers = new AbortController();
  let frame, observer, mixer, disposed = false, object;
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    cancelAnimationFrame(frame);
    handlers.abort(); keys.clear(); observer?.disconnect(); controls.dispose();
    mixer?.stopAllAction(); if (mixer && object) mixer.uncacheRoot(object);
    const geometry = new Set(), materials = new Set(), textures = new Set();
    scene.traverse(node => {
      if (node.geometry) geometry.add(node.geometry);
      for (const material of (Array.isArray(node.material) ? node.material : [node.material]).filter(Boolean)) materials.add(material);
      if (node.skeleton) node.skeleton.dispose();
    });
    for (const material of materials) {
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
      material.dispose();
    }
    for (const texture of textures) { texture.image?.close?.(); texture.dispose(); }
    for (const item of geometry) item.dispose();
    renderer.dispose(); renderer.forceContextLoss(); canvas.remove();
  };
  try {
    const gltf = await new GLTFLoader().loadAsync(url);
    object = gltf.scene;
    actor.add(object); // Own even a rejected model so the error path disposes its resources.
    const clip = gltf.animations.find(candidate => candidate.name === 'Walk_inplace');
    if (!clip || !Number.isFinite(clip.duration) || clip.duration <= 0) throw new Error('A valid Walk_inplace clip is required; forward clips cannot drive this controller.');
    mixer = new THREE.AnimationMixer(object);
    const walking = mixer.clipAction(clip);
    walking.play(); mixer.update(0);
    const normalized = new THREE.Group();
    actor.remove(object); normalized.add(object); actor.add(normalized);
    normalized.rotation.y = -Math.PI / 2; // Existing canine exports move along +X; runtime forward is +Z.
    normalized.updateMatrixWorld(true);
    let bounds = new THREE.Box3().setFromObject(normalized);
    const extent = bounds.getSize(new THREE.Vector3());
    const length = Math.max(extent.x, extent.z);
    if (bounds.isEmpty() || ![length, extent.y].every(Number.isFinite) || length <= 0 || extent.y <= 0) throw new Error('Character has invalid geometry bounds.');
    const scale = 2 / length;
    normalized.scale.setScalar(scale); normalized.updateMatrixWorld(true);
    bounds = new THREE.Box3().setFromObject(normalized);
    const center = bounds.getCenter(new THREE.Vector3());
    normalized.position.set(-center.x, -bounds.min.y, -center.z);
    const height = bounds.max.y - bounds.min.y;
    const holdTracks = clip.tracks.map(track => {
      const hold = track.clone(), width = track.getValueSize();
      hold.times = new Float32Array([0, 1]);
      hold.values = new Float32Array([...track.values.slice(0, width), ...track.values.slice(0, width)]);
      return hold;
    });
    const standing = mixer.clipAction(new THREE.AnimationClip('Standing_hold', 1, holdTracks));
    walking.stop(); standing.play();
    object.traverse(node => { if (node.isSkinnedMesh) node.frustumCulled = false; });
    scene.add(new THREE.HemisphereLight(0xffffff, 0x657561, 2));
    const light = new THREE.DirectionalLight(0xffffff, 2.5); light.position.set(3, 6, 4); scene.add(light);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(18, 18), new THREE.MeshStandardMaterial({color: 0xc3d3bf}));
    floor.rotation.x = -Math.PI / 2; floor.position.y = -.005; scene.add(floor);
    scene.add(new THREE.GridHelper(18, 18, 0x748b72, 0xa6b9a2));
    const obstacles = [
      {minX: 3, maxX: 4, minZ: -1, maxZ: 1},
      {minX: -9, maxX: -8, minZ: -9, maxZ: 9}, {minX: 8, maxX: 9, minZ: -9, maxZ: 9},
      {minX: -9, maxX: 9, minZ: -9, maxZ: -8}, {minX: -9, maxX: 9, minZ: 8, maxZ: 9},
    ];
    for (const box of obstacles) {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(box.maxX - box.minX, 1, box.maxZ - box.minZ), new THREE.MeshStandardMaterial({color: 0x788c88}));
      mesh.position.set((box.minX + box.maxX)/2, .5, (box.minZ + box.maxZ)/2); scene.add(mesh);
    }
    const nominalSpeed = stride * scale / clip.duration;
    const controller = new CharacterController({maxSpeed: nominalSpeed, radius: 1, obstacles});
    const clear = () => keys.clear();
    const signal = handlers.signal;
    const codes = new Set(['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowLeft','ArrowDown','ArrowRight']);
    canvas.addEventListener('keydown', event => { if (codes.has(event.code)) { keys.add(event.code); event.preventDefault(); } }, {signal});
    canvas.addEventListener('keyup', event => { if (codes.has(event.code)) { keys.delete(event.code); event.preventDefault(); } }, {signal});
    canvas.addEventListener('pointerdown', () => canvas.focus(), {signal});
    canvas.addEventListener('blur', clear, {signal});
    window.addEventListener('blur', clear, {signal});
    document.addEventListener('visibilitychange', clear, {signal});
    let previous = performance.now(), moving = false;
    const reset = () => {
      clear(); controller.reset(); actor.position.set(0,0,0); actor.rotation.y = 0;
      controls.target.set(0, height * .5, 0); camera.position.set(4, 3, 5); controls.update();
      mixer.stopAllAction(); standing.reset().setEffectiveWeight(1).play(); mixer.update(0);
      moving = false; previous = performance.now(); onMotion(false);
      container.dataset.x = container.dataset.z = '0';
    };
    reset();
    observer = new ResizeObserver(() => {
      const width = Math.max(1, container.clientWidth), height = Math.max(1, container.clientHeight);
      renderer.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix();
    }); observer.observe(container);
    const direction = new THREE.Vector3(), right = new THREE.Vector3();
    const tick = now => {
      if (disposed) return;
      const delta = Math.max(0, Math.min((now - previous) / 1000, .25)); previous = now;
      const forwardInput = Number(keys.has('KeyW') || keys.has('ArrowUp')) - Number(keys.has('KeyS') || keys.has('ArrowDown'));
      const sideInput = Number(keys.has('KeyD') || keys.has('ArrowRight')) - Number(keys.has('KeyA') || keys.has('ArrowLeft'));
      camera.getWorldDirection(direction); direction.y = 0; direction.normalize();
      right.crossVectors(direction, camera.up).normalize();
      const oldX = controller.x, oldZ = controller.z;
      controller.update(delta, {x: direction.x * forwardInput + right.x * sideInput, z: direction.z * forwardInput + right.z * sideInput});
      actor.position.set(controller.x, 0, controller.z); actor.rotation.y = controller.yaw;
      const travel = new THREE.Vector3(controller.x - oldX, 0, controller.z - oldZ);
      camera.position.add(travel); controls.target.add(travel);
      const nextMoving = controller.speed > .001;
      if (nextMoving !== moving) {
        (nextMoving ? walking : standing).reset().play().crossFadeFrom(nextMoving ? standing : walking, .15, false);
        moving = nextMoving; onMotion(moving);
      }
      walking.timeScale = Math.max(.5, Math.min(1.5, controller.speed / nominalSpeed));
      mixer.update(delta); controls.update(); renderer.render(scene, camera);
      container.dataset.x = String(controller.x); container.dataset.z = String(controller.z);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return {dispose, reset};
  } catch (error) { dispose(); throw error; }
}
