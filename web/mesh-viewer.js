import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export async function loadMeshViewer(container, url) {
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
  let object, frame, observer, disposed = false;
  const initial = new THREE.Vector3();
  const dispose = () => {
    disposed = true;
    cancelAnimationFrame(frame);
    observer?.disconnect();
    controls.dispose();
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
    const box = new THREE.Box3().setFromObject(object);
    if (box.isEmpty()) throw new Error('The GLB contains no visible mesh.');
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    object.position.sub(center);
    scene.add(object);
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
    const animate = () => {
      if (disposed) return;
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };
    animate();
    return {
      dispose,
      reset() { camera.position.copy(initial); controls.target.set(0, 0, 0); controls.update(); },
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
