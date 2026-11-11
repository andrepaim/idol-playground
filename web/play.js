import './style.css';
import { loadPlayable } from './playable-viewer.js';

const view = document.getElementById('play-view');
const status = document.getElementById('play-status');
const reset = document.getElementById('play-reset');
let viewer;
try {
  const params = new URLSearchParams(location.search);
  const model = params.get('model') || '';
  if (!/^\/outputs\/[a-zA-Z0-9_-]+\/walk-inplace\.glb$/.test(model)) throw new Error('Choose a same-origin completed in-place canine result from the studio.');
  if (params.get('profile') !== 'canine-34-v1') throw new Error('This scene requires the reviewed canine-34-v1 profile.');
  const stride = Number(params.get('stride'));
  if (!Number.isFinite(stride) || stride <= 0 || stride > 100) throw new Error('Invalid canine stride.');
  viewer = await loadPlayable(view, model, {stride, onMotion(moving) {
    document.getElementById('play-motion').textContent = moving ? 'Walking' : 'Standing';
  }});
  status.textContent = 'Ready · click the scene to play.';
  reset.disabled = false;
  reset.addEventListener('click', () => viewer.reset());
} catch (error) {
  status.textContent = `Unable to play: ${error.message}`;
}
window.addEventListener('pagehide', () => viewer?.dispose(), {once: true});
