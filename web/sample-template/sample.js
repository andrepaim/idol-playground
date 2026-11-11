import { loadPlayable } from './playable-viewer.js';
let viewer;
const status = document.getElementById('status');
const button = document.getElementById('reset');
try {
  const response = await fetch('./character.json');
  if (!response.ok) throw new Error('Missing character manifest.');
  const manifest = await response.json();
  if (manifest.schema_version !== 1 || manifest.profile !== 'canine-34-v1' || manifest.motion?.mode !== 'inplace' || !Number.isFinite(manifest.motion.stride) || manifest.motion.stride <= 0) {
    throw new Error('Unsupported character manifest.');
  }
  if (manifest.geometry?.file !== 'character.glb' || !/^[a-f0-9]{64}$/.test(manifest.geometry.sha256)) throw new Error('Invalid character SHA-256 metadata.');
  const model = await fetch('./character.glb');
  if (!model.ok) throw new Error('Missing character GLB.');
  const bytes = await model.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  if (hash !== manifest.geometry.sha256) throw new Error('Character SHA-256 mismatch. Export the sample again.');
  const url = URL.createObjectURL(new Blob([bytes], {type: 'model/gltf-binary'}));
  try { viewer = await loadPlayable(document.getElementById('play-view'), url, {stride: manifest.motion.stride}); }
  finally { URL.revokeObjectURL(url); }
  status.textContent = 'Ready · click the scene to play.';
  button.disabled = false;
  button.addEventListener('click', () => viewer.reset());
} catch (error) { status.textContent = `Unable to play: ${error.message}`; }
window.addEventListener('pagehide', () => viewer?.dispose(), {once: true});
