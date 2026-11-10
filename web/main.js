import './style.css';

const $ = (id) => document.getElementById(id);
let viewer, renderer, resizeObserver, previewUrl, busy = false, serverReady = false;
let latestProgress, progressReceivedAt, generationStartedAt;
const stages = ['load', 'preprocess', 'encode', 'sampling', 'decode', 'save', 'preview'];

function duration(seconds) {
  const rounded = Math.max(1, Math.ceil(seconds));
  return rounded < 60 ? `${rounded}s` : `${Math.floor(rounded / 60)}m ${rounded % 60}s`;
}

function updateTiming() {
  const sinceProgress = (Date.now() - progressReceivedAt) / 1000;
  const elapsed = latestProgress?.elapsed_seconds != null
    ? latestProgress.elapsed_seconds + sinceProgress : (Date.now() - generationStartedAt) / 1000;
  $('elapsed').textContent = `${Math.floor(elapsed)}s elapsed`;
  if (latestProgress?.stage === 'preview') {
    $('eta').textContent = 'Generation complete · opening preview';
  } else if (latestProgress?.eta_seconds != null) {
    const remaining = latestProgress.eta_seconds - sinceProgress;
    $('eta').textContent = remaining > 0
      ? `About ${duration(remaining)} remaining${latestProgress.eta_basis === 'approximate' ? ' · rough estimate' : ''}`
      : 'Taking longer than estimated…';
  } else {
    $('eta').textContent = latestProgress?.stage === 'download'
      ? 'ETA available after download' : 'Estimating time remaining…';
  }
}

function showProgress(job) {
  latestProgress = job;
  progressReceivedAt = Date.now();
  $('progress').textContent = job.message;
  const index = stages.indexOf(job.stage);
  $('stage-list').querySelectorAll('[data-stage]').forEach((item, itemIndex) => {
    item.classList.toggle('done', index > itemIndex);
    item.classList.toggle('current', index === itemIndex);
    if (index === itemIndex) item.setAttribute('aria-current', 'step');
    else item.removeAttribute('aria-current');
  });
  if (job.stage === 'sampling' && job.step != null) {
    $('generation-bar').max = job.total_steps;
    $('generation-bar').value = job.step;
    $('step-detail').textContent = `Sampling step ${job.step} of ${job.total_steps}`;
  } else {
    $('generation-bar').removeAttribute('value');
    $('step-detail').textContent = job.stage === 'preview' ? 'Preparing the interactive viewer…' : '';
  }
  updateTiming();
}

function showError(message) {
  $('message').textContent = message;
  $('message').hidden = false;
}

async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check your generation settings and try again.');
  return data;
}

function updateButton() {
  $('generate').disabled = busy || !serverReady || !$('image').files.length;
}

function selectImage() {
  const file = $('image').files[0];
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 20 * 1024 * 1024) {
    $('image').value = '';
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    $('image-preview').hidden = true;
    $('upload-prompt').hidden = false;
    $('replace').hidden = true;
    updateButton();
    return showError('Choose a PNG, JPEG, or WebP image up to 20 MB.');
  }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  $('image-preview').src = previewUrl;
  $('image-preview').hidden = false;
  $('upload-prompt').hidden = true;
  $('replace').hidden = false;
  $('message').hidden = true;
  updateButton();
}

$('image').addEventListener('change', selectImage);
$('dropzone').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); $('image').click(); }
});
for (const name of ['dragenter', 'dragover', 'dragleave', 'drop']) {
  $('dropzone').addEventListener(name, (event) => {
    event.preventDefault();
    $('dropzone').classList.toggle('over', name === 'dragenter' || name === 'dragover');
    if (name === 'drop' && !busy && event.dataTransfer.files.length) {
      const transfer = new DataTransfer();
      transfer.items.add(event.dataTransfer.files[0]);
      $('image').files = transfer.files;
      selectImage();
    }
  });
}

async function disposeViewer() {
  resizeObserver?.disconnect();
  try {
    if (viewer) await viewer.dispose();
  } finally {
    // Own the renderer explicitly: the viewer's default disposal assumes a body-level root.
    renderer?.dispose();
    renderer?.forceContextLoss();
    viewer = undefined;
    renderer = undefined;
    $('viewer').replaceChildren();
  }
}

async function loadViewer(url) {
  const [{ Viewer }, { WebGLRenderer }] = await Promise.all([
    import('@mkkellogg/gaussian-splats-3d'), import('three'),
  ]);
  await disposeViewer();
  const container = $('viewer');
  renderer = new WebGLRenderer({ antialias: false, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  container.appendChild(renderer.domElement);
  viewer = new Viewer({
    rootElement: container, renderer, cameraUp: [0, -1, 0],
    initialCameraPosition: [1, -0.35, 1.65], initialCameraLookAt: [0, 0, 0],
    sharedMemoryForWorkers: false, gpuAcceleratedSort: false,
    sphericalHarmonicsDegree: 0,
  });
  resizeObserver = new ResizeObserver(() => {
    renderer?.setSize(container.clientWidth, container.clientHeight);
    viewer?.forceRenderNextFrame();
  });
  resizeObserver.observe(container);
  await viewer.addSplatScene(url, {
    splatAlphaRemovalThreshold: 5, showLoadingUI: false, progressiveLoad: false,
    onProgress: (percent, label, status) => {
      // GaussianSplats3D 0.4.7 reports Downloading as 0; this enum is not exported.
      const action = status === 0 ? 'Downloading the 3D object' : 'Preparing the preview';
      $('step-detail').textContent = `${action}${Number.isFinite(percent) ? ` · ${Math.round(percent)}%` : ''}`;
    },
  });
  viewer.start();
}

async function watchJob(id) {
  while (true) {
    const job = await request(`/api/jobs/${id}`);
    showProgress(job);
    if (job.state === 'error') throw new Error(job.message);
    if (job.state === 'complete') {
      $('download').href = job.files['object.ply'];
      $('download').hidden = false;
      $('result-info').textContent = `${Number(job.settings.num_gaussians).toLocaleString()} Gaussians · ${job.seconds}s · seed ${job.settings.seed}`;
      showProgress({ stage: 'preview', message: 'Downloading the PLY and preparing the interactive 3D preview…' });
      try {
        await loadViewer(job.files['object.ply']);
        $('empty').hidden = true;
      } catch (error) {
        $('empty').hidden = false;
        showError(`Generation succeeded, but the 3D preview could not load. You can download the PLY. ${error.message}`);
      }
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 750));
  }
}

$('form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  updateButton();
  const formData = new FormData($('form'));
  $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = true; });
  $('message').hidden = true;
  $('download').hidden = true;
  $('empty').hidden = true;
  $('busy').hidden = false;
  $('result-info').textContent = 'Generation in progress…';
  generationStartedAt = Date.now();
  showProgress({ stage: 'starting', message: 'Uploading your image and starting the generation…' });
  const tick = setInterval(updateTiming, 1000);
  try {
    await disposeViewer();
    const job = await request('/api/generate', { method: 'POST', body: formData });
    await watchJob(job.id);
  } catch (error) {
    showError(error.message);
    $('result-info').textContent = 'Generation could not finish.';
    if (!viewer) $('empty').hidden = false;
  } finally {
    clearInterval(tick);
    $('busy').hidden = true;
    $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = false; });
    busy = false;
    updateButton();
  }
});

async function checkStatus() {
  try {
    const status = await request('/api/status');
    serverReady = status.ready;
    $('backend-label').textContent = status.weights_downloaded
      ? 'Models downloaded · inference runs on your GPU.'
      : 'Inference runs on your GPU. First run downloads the model weights.';
    if (!status.ready) {
      $('setup').innerHTML = '<strong>Finish local setup to generate.</strong> Install the model dependencies with <code>uv sync --extra local</code>. Model weights download automatically from public repositories; no Hugging Face login is required.';
      $('setup').hidden = false;
    } else {
      $('setup').hidden = true;
    }
    updateButton();
  } catch {
    serverReady = false;
    updateButton();
    showError('Could not reach the model server. Start it with uv run uvicorn app:app --host 127.0.0.1 --port 8000.');
  }
}
checkStatus();
setInterval(() => { if (!busy && !serverReady) checkStatus(); }, 10000);
