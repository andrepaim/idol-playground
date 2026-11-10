import './style.css';

const $ = (id) => document.getElementById(id);
let viewer, renderer, resizeObserver, previewUrl, busy = false, serverReady = false;
let latestProgress, progressReceivedAt, generationStartedAt, meshViewer, activeJobId, cachedStatus;
const splatStages = [['load','Load'], ['preprocess','Prepare'], ['encode','Analyze'], ['sampling','Generate'], ['decode','Build'], ['save','Save'], ['preview','Preview']];
const meshStages = [['preprocess','Prepare'], ['load','Load'], ['reconstruct','Generate'], ['extract','Surface'], ['simplify','Optimize'], ['texture','Texture'], ['export','Save'], ['preview','Preview']];
const rigStages = [['rig_prepare','Prepare'],['skeleton','Bones'],['rig_bind','Bind'],['skinning','Weights'],['rig_export','Export'],['rig_verify','Check'],['preview','Preview']];
const conversionStages = [['capture','Views'],['stereo','Depth'],['surface','Surface'],['export','Save'],['preview','Preview']];
const idolMeshStages = [...splatStages.filter(([stage]) => stage !== 'preview'),...conversionStages];
let lastMeshJob, lastSplatJob, lastRigJob, walkProfile;
const walkStages = [['walk_prepare','Weights'],['walk_pose','Stance'],['walk_bake','Contact'],['walk_export','Export'],['walk_verify','Check'],['preview','Preview']];
let stages = splatStages.map(([stage]) => stage);

function isMesh() { return $('output_type').value === 'mesh'; }

function isIdolMesh() { return isMesh() && $('mesh_backend').value === 'idol'; }

function syncOutputControls() {
  const idol = !isMesh() || isIdolMesh();
  $('splat-options').hidden = !idol;
  $('mesh-options').hidden = !isMesh();
  $('mesh-method-field').hidden = !isMesh();
  $('mesh_backend').disabled = busy || !isMesh();
  $('splat-options').querySelectorAll('input,select').forEach((input) => { input.disabled = busy || !idol; });
  $('legacy-mesh-options').hidden = isIdolMesh();
  $('legacy-mesh-options').querySelectorAll('input,select').forEach((input) => { input.disabled = busy || !isMesh() || isIdolMesh(); });
  $('splat-surface-options').hidden = !isIdolMesh();
  $('splat-surface-options').querySelectorAll('input,select').forEach((input) => { input.disabled = busy || !isIdolMesh(); });
  $('mesh-note').textContent = isIdolMesh() ? 'Mesh from the Idol result, with embedded vertex colors. Main-subject mode can omit detached parts. Inspect before rigging.' : 'Independent image reconstruction. Inspect the mesh before animation.';
}

function configureStages(rig = false, conversion = false, walk = false) {
  const definitions = walk ? walkStages : rig ? rigStages : conversion ? conversionStages : isIdolMesh() ? idolMeshStages : (isMesh() ? meshStages : splatStages);
  stages = definitions.map(([stage]) => stage);
  $('stage-list').replaceChildren(...definitions.map(([stage, label]) => {
    const item = document.createElement('span');
    item.dataset.stage = stage;
    item.textContent = label;
    return item;
  }));
}

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
  if (['sampling', 'extract', 'texture', 'capture', 'stereo', 'walk_bake'].includes(job.stage) && job.step != null && job.total_steps > 0) {
    $('generation-bar').max = job.total_steps;
    $('generation-bar').value = job.step;
    $('step-detail').textContent = job.stage === 'walk_bake' ? `Contact frame ${job.step} of ${job.total_steps}` : job.stage === 'capture' ? `Rendered image ${job.step} of ${job.total_steps}` : job.stage === 'stereo' ? `Depth pair ${job.step} of ${job.total_steps}` : job.stage === 'sampling' ? `Sampling step ${job.step} of ${job.total_steps}` : `${job.stage === 'texture' ? 'Texture' : 'Surface'} samples · ${Math.round(job.step / job.total_steps * 100)}%`;
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
  updateWalkControls();
  $('saved-result').disabled = busy;
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
  meshViewer?.dispose();
  meshViewer = undefined;
  $('mesh-toolbar').hidden = true;
  $('walk-playback').hidden = true;
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
    if (job.state === 'cancelled') {
      $('result-info').textContent = 'Generation cancelled.';
      $('empty').hidden = false;
      return;
    }
    if (job.state === 'complete') {
      if (job.output_type === 'walk') { await showWalk(job); refreshSavedResults(); return; }
      lastRigJob = undefined;
      $('walk-actions').hidden = true;
      $('walk-exports').hidden = true;
      const rig = job.output_type === 'rig';
      const mesh = rig || job.output_type === 'mesh' || Boolean(job.files['object.glb']);
      const file = rig ? job.files['rigged.glb'] : (mesh ? job.files['object.glb'] : job.files['object.ply']);
      lastMeshJob = rig ? job.source_job : (mesh ? id : undefined);
      lastSplatJob = mesh ? undefined : id;
      const colored = mesh && !rig && job.mesh.appearance === 'vertex_colors';
      $('source-download').hidden = !job.files['source.ply'];
      if (job.files['source.ply']) $('source-download').href = job.files['source.ply'];
      const warnings = (rig ? job.rig : job.mesh)?.warnings || [];
      $('mesh-warnings').hidden = !warnings.length;
      $('mesh-warnings').textContent = warnings.join(' ');
      $('download').href = file;
      $('download').download = mesh ? 'idol-mesh.glb' : 'idol-object.ply';
      $('download').textContent = mesh ? 'Download .glb ↓' : 'Download .ply ↓';
      $('result-badge').textContent = rig ? 'EXPERIMENTAL CHARACTER RIG' : colored ? 'SPLAT-DERIVED MESH' : mesh ? 'TEXTURED POLYGON MESH' : '3D GAUSSIAN SPLAT';
      $('download').hidden = false;
      $('result-info').textContent = rig ? `${job.rig.bones} bones · ${Number(job.rig.triangles).toLocaleString()} triangles · ${job.seconds}s` : mesh ? `${Number(job.mesh.triangles).toLocaleString()} triangles · ${colored ? 'vertex colors' : `${job.mesh.texture_resolution}px texture`} · ${job.seconds}s` : `${Number(job.settings.num_gaussians).toLocaleString()} Gaussians · ${job.seconds}s · seed ${job.settings.seed}`;
      showProgress({ stage: 'preview', message: mesh ? 'Opening the mesh preview…' : 'Downloading the PLY and preparing the interactive 3D preview…' });
      try {
        if (mesh) {
          await disposeViewer();
          const { loadMeshViewer } = await import('./mesh-viewer.js');
          meshViewer = await loadMeshViewer($('viewer'), file);
          $('wireframe').checked = false;
          $('mesh-toolbar').hidden = false;
          $('skeleton').checked = false;
          $('bend').checked = false;
          $('skeleton-control').hidden = !meshViewer.hasSkeleton;
          $('bend-control').hidden = !meshViewer.hasAnimation;
        } else {
          await loadViewer(file);
        }
        $('empty').hidden = true;
      } catch (error) {
        $('empty').hidden = false;
        showError(`Generation succeeded, but the 3D preview could not load. You can download the ${mesh ? 'GLB' : 'PLY'}. ${error.message}`);
      }
      $('rig-exports').hidden = !rig;
      if (rig) {
        $('fbx-download').href = job.files['rigged.fbx'];
        $('blend-download').href = job.files['character.blend'];
        $('static-download').href = `/outputs/${job.source_job}/object.glb`;
        lastRigJob = id;
        await loadWalkProfile();
      }
      updateRigControls();
      updateConversionControls();
      refreshSavedResults();
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 750));
  }
}

$('form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  lastMeshJob = undefined;
  lastSplatJob = undefined;
  $('conversion-actions').hidden = true;
  $('source-download').hidden = true;
  $('mesh-warnings').hidden = true;
  $('rig-actions').hidden = true;
  $('rig-exports').hidden = true;
  lastRigJob = undefined;
  $('walk-actions').hidden = true;
  $('walk-exports').hidden = true;
  updateButton();
  const formData = new FormData($('form'));
  $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = true; });
  configureStages();
  activeJobId = undefined;
  $('cancel').hidden = !isMesh();
  $('cancel').disabled = true;
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
    activeJobId = job.id;
    $('cancel').disabled = false;
    await watchJob(job.id);
  } catch (error) {
    showError(error.message);
    $('result-info').textContent = 'Generation could not finish.';
    if (!viewer && !meshViewer) $('empty').hidden = false;
  } finally {
    clearInterval(tick);
    $('busy').hidden = true;
    $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = false; });
    busy = false;
    activeJobId = undefined;
    $('cancel').hidden = true;
    syncOutputControls();
    updateButton();
    updateRigControls();
    updateConversionControls();
  }
});

function applyStatus() {
  if (!cachedStatus) return;
  $('engine-credit').innerHTML = isIdolMesh() ? 'Powered by Idol · stereo depth · surface fusion' : isMesh() ? 'Powered by <a href="https://github.com/VAST-AI-Research/TripoSR" target="_blank" rel="noreferrer">TripoSR</a> · Mesh reconstruction' : 'Powered by <a href="https://github.com/speridlabs/idol-sdk" target="_blank" rel="noreferrer">Idol</a> · Gaussian splatting';
  const status = isIdolMesh() ? cachedStatus.splat_mesh : isMesh() ? cachedStatus.mesh : cachedStatus;
  serverReady = Boolean(status?.ready) && (!isIdolMesh() || Boolean(status?.upload_ready && status?.weights_downloaded));
  $('backend-label').textContent = isIdolMesh() ? 'Local splat-to-mesh generation · rendering views can take several minutes.' : isMesh()
    ? (status?.weights_downloaded ? 'Models downloaded · mesh generation runs locally.' : 'Local mesh generation. First use downloads its model files.')
    : (status?.weights_downloaded ? 'Models downloaded · inference runs on your GPU.' : 'Inference runs on your GPU. First run downloads the model weights.');
  if (!serverReady) {
    $('setup').innerHTML = isIdolMesh() ? '<strong>Finish splat-to-mesh setup.</strong> Run <code>make setup-splat-mesh splat-mesh-models</code>. Image uploads also need <code>make setup-local models</code>.' : isMesh()
      ? '<strong>Finish mesh setup to generate.</strong> Run <code>make setup-mesh mesh-models</code>. Mesh generation uses its own environment and public model files.'
      : '<strong>Finish local setup to generate.</strong> Install the model dependencies with <code>uv sync --extra local</code>. Model weights download automatically from public repositories; no Hugging Face login is required.';
    $('setup').hidden = false;
  } else {
    $('setup').hidden = true;
  }
  syncOutputControls();
  updateButton();
  updateRigControls();
  updateConversionControls();
}

async function checkStatus() {
  try {
    cachedStatus = await request('/api/status');
    applyStatus();
  } catch {
    serverReady = false;
    updateButton();
    showError('Could not reach the model server. Start it with ./run.sh.');
  }
}

$('output_type').addEventListener('change', () => { syncOutputControls(); applyStatus(); });
$('mesh_backend').addEventListener('change', () => { syncOutputControls(); applyStatus(); });
$('wireframe').addEventListener('change', () => meshViewer?.wireframe($('wireframe').checked));
$('reset-view').addEventListener('click', () => meshViewer?.reset());
$('cancel').addEventListener('click', async () => {
  if (!activeJobId) return;
  $('cancel').disabled = true;
  try { await request(`/api/jobs/${activeJobId}/cancel`, { method: 'POST' }); }
  catch (error) { showError(error.message); }
});
syncOutputControls();
checkStatus();
setInterval(() => { if (!busy) checkStatus(); }, 10000);

function updateRigControls() {
  $('rig-actions').hidden = !lastMeshJob;
  const ready = cachedStatus?.rig?.ready && cachedStatus?.rig?.weights_downloaded;
  $('auto-rig').disabled = busy || !ready;
  $('rig-note').textContent = ready ? 'Inspect the mesh first. Automatic rigging cannot repair missing or fused limbs.' : 'For automatic rigging, run make setup-rig rig-models.';
}
$('skeleton').addEventListener('change', () => meshViewer?.skeleton($('skeleton').checked));
$('bend').addEventListener('change', () => meshViewer?.diagnostic($('bend').checked));
$('auto-rig').addEventListener('click', async () => {
  if (busy || !lastMeshJob) return;
  busy = true;
  configureStages(true);
  updateRigControls();
  updateButton();
  $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = true; });
  $('cancel').hidden = false;
  $('cancel').disabled = true;
  $('message').hidden = true;
  $('download').hidden = true;
  $('rig-exports').hidden = true;
  $('empty').hidden = true;
  $('busy').hidden = false;
  generationStartedAt = Date.now();
  showProgress({ stage: 'starting', message: 'Starting local automatic rigging…' });
  const tick = setInterval(updateTiming, 1000);
  try {
    const job = await request(`/api/jobs/${lastMeshJob}/rig`, { method: 'POST' });
    activeJobId = job.id;
    $('cancel').disabled = false;
    await disposeViewer();
    await watchJob(job.id);
  } catch (error) {
    showError(error.message);
    $('result-info').textContent = 'Rigging could not finish. The original mesh is preserved.';
    if (!meshViewer) $('empty').hidden = false;
  } finally {
    clearInterval(tick);
    busy = false;
    activeJobId = undefined;
    $('busy').hidden = true;
    $('cancel').hidden = true;
    $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = false; });
    syncOutputControls();
    updateButton();
    updateRigControls();
  }
});

function updateConversionControls() {
  $('conversion-actions').hidden = !lastSplatJob;
  const ready = cachedStatus?.splat_mesh?.ready && cachedStatus?.splat_mesh?.weights_downloaded;
  $('convert-mesh').disabled = busy || !ready;
  $('conversion-note').textContent = ready ? 'Reuse this completed splat. Conversion uses the surface and parts settings from the Idol mesh method.' : 'Set up conversion with make setup-splat-mesh splat-mesh-models.';
}
$('convert-mesh').addEventListener('click', async () => {
  if (busy || !lastSplatJob) return;
  busy = true;
  configureStages(false,true);
  updateButton();
  updateConversionControls();
  $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = true; });
  $('cancel').hidden = false;
  $('cancel').disabled = true;
  $('message').hidden = true;
  $('mesh-warnings').hidden = true;
  $('download').hidden = true;
  $('source-download').hidden = true;
  $('empty').hidden = true;
  $('busy').hidden = false;
  generationStartedAt = Date.now();
  showProgress({stage:'starting',message:'Starting mesh conversion from the completed splat…'});
  const tick = setInterval(updateTiming,1000);
  try {
    const body = new URLSearchParams({surface_quality:$('surface_quality').value,component_mode:$('component_mode').value});
    const job = await request(`/api/jobs/${lastSplatJob}/mesh`,{method:'POST',body});
    activeJobId = job.id;
    $('cancel').disabled = false;
    await disposeViewer();
    await watchJob(job.id);
  } catch (error) {
    showError(error.message);
    $('result-info').textContent = 'Mesh conversion could not finish. The original splat is preserved.';
    if (!viewer && !meshViewer) $('empty').hidden = false;
  } finally {
    clearInterval(tick);
    busy = false;
    activeJobId = undefined;
    $('busy').hidden = true;
    $('cancel').hidden = true;
    $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = false; });
    syncOutputControls();
    updateButton();
    updateRigControls();
    updateConversionControls();
  }
});

async function refreshSavedResults() {
  try {
    const data = await request('/api/jobs');
    const options = (data.jobs || []).map((job) => {
      const option = document.createElement('option');
      option.value = job.id;
      const kind = job.output_type === 'walk' ? 'Walk' : job.output_type === 'rig' ? 'Rig' : job.output_type === 'mesh' ? 'Mesh' : 'Splat';
      option.textContent = `${kind} · ${job.started_at ? new Date(job.started_at * 1000).toLocaleString() : job.id.slice(0,8)}`;
      return option;
    });
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Recent completed results…';
    $('saved-result').replaceChildren(placeholder,...options);
  } catch { /* Saved results are optional while the server is unavailable. */ }
}
$('saved-result').addEventListener('change',async () => {
  const id = $('saved-result').value;
  if (!id || busy) return;
  busy = true;
  updateButton();
  $('saved-result').disabled = true;
  $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = true; });
  $('message').hidden = true;
  $('busy').hidden = false;
  generationStartedAt = Date.now();
  try {
    const job = await request(`/api/jobs/${id}`);
    if (job.state !== 'complete') throw new Error('This saved result is not complete.');
    $('output_type').value = job.output_type === 'splat' || !job.output_type ? 'splat' : 'mesh';
    if (job.output_type === 'mesh') $('mesh_backend').value = job.mesh_backend || 'triposr';
    configureStages(job.output_type === 'rig', false, job.output_type === 'walk');
    await disposeViewer();
    await watchJob(id);
  } catch (error) { showError(error.message); }
  finally {
    busy = false;
    $('busy').hidden = true;
    $('saved-result').disabled = false;
    $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = false; });
    applyStatus();
    updateRigControls();
    updateConversionControls();
  }
});
refreshSavedResults();

function updateWalkControls() {
  const available = Boolean(walkProfile?.supported && cachedStatus?.walk?.ready);
  $('create-walk').disabled = busy || !available || !$('walk-reviewed').checked;
  $('paw-review').hidden = !available;
  if (walkProfile && lastRigJob) $('walk-note').textContent = cachedStatus?.walk?.ready ? walkProfile.reason : 'Walking needs the Blender environment. Run make setup-rig.';
  $('walk-actions').querySelectorAll('select,input').forEach((input) => { input.disabled = busy; });
}
async function loadWalkProfile() {
  $('walk-reviewed').checked = false;
  walkProfile = undefined;
  $('walk-actions').hidden = !lastRigJob;
  if (!lastRigJob) return;
  try {
    walkProfile = await request(`/api/jobs/${lastRigJob}/walk-profile`);
    $('walk-note').textContent = cachedStatus?.walk?.ready ? walkProfile.reason : 'Walking needs the Blender environment. Run make setup-rig.';
    if (walkProfile.supported) {
      for (const [role,name] of Object.entries(walkProfile.paws)) $(`paw-${role}`).value = name;
    }
  } catch (error) { $('walk-note').textContent = error.message; }
  updateWalkControls();
}
async function showWalk(job) {
  lastRigJob = job.source_job;
  lastMeshJob = undefined;
  lastSplatJob = undefined;
  $('rig-actions').hidden = true;
  $('conversion-actions').hidden = true;
  $('rig-exports').hidden = true;
  $('source-download').hidden = true;
  $('result-badge').textContent = 'EXPERIMENTAL CANINE WALK';
  $('result-info').textContent = `${job.walk.bones} bones · ${job.walk.duration}s cycle · ${job.settings.speed}`;
  $('mesh-warnings').textContent = (job.walk.warnings || []).join(' ');
  $('mesh-warnings').hidden = false;
  $('download').href = job.files['animated.glb'];
  $('download').textContent = 'Download animated .glb ↓';
  $('download').download = 'idol-walk.glb';
  $('download').hidden = false;
  for (const [id,name] of Object.entries({'walk-inplace':'walk-inplace.glb','walk-forward':'walk-forward.glb','walk-fbx':'animated.fbx','walk-blend':'character.blend','walk-report':'walk.json'})) $(id).href = job.files[name];
  $('walk-source').href = `/outputs/${job.source_job}/rigged.glb`;
  $('walk-exports').hidden = false;
  showProgress({stage:'preview',message:'Opening the walking preview…'});
  try {
    await disposeViewer();
    const {loadMeshViewer} = await import('./mesh-viewer.js');
    meshViewer = await loadMeshViewer($('viewer'),job.files['animated.glb'],{
      walking:true, stride:job.settings.motion === 'forward' ? job.walk.stride : 0,
      ground:job.walk.ground_z,
      onTime(time,duration) { $('walk-time').max = duration; $('walk-time').value = time; },
    });
    $('mesh-toolbar').hidden = false;
    $('skeleton-control').hidden = false;
    $('bend-control').hidden = true;
    $('skeleton').checked = $('wireframe').checked = false;
    $('walk-playback').hidden = false;
    $('walk-play').textContent = 'Pause';
    $('walk-floor').checked = $('walk-follow').checked = true;
    $('walk-play-speed').value = '1';
    $('empty').hidden = true;
  } catch (error) { $('empty').hidden = false; showError(`Walk saved, but preview failed. ${error.message}`); }
  await loadWalkProfile();
  for (const [role,name] of Object.entries(job.settings.paws || {})) $(`paw-${role}`).value = name;
}
$('walk-reviewed').addEventListener('change',updateWalkControls);
for (const role of ['fore_left','fore_right','hind_left','hind_right']) {
  const select = $(`paw-${role}`);
  select.addEventListener('focus',() => meshViewer?.highlight(select.value));
  select.addEventListener('change',() => { meshViewer?.highlight(select.value); $('walk-reviewed').checked = false; updateWalkControls(); });
}
$('walk-play').addEventListener('click',() => {
  const playing = $('walk-play').textContent === 'Pause';
  meshViewer?.play(!playing); $('walk-play').textContent = playing ? 'Play' : 'Pause';
});
$('walk-restart').addEventListener('click',() => { meshViewer?.restart(); $('walk-play').textContent = 'Pause'; });
$('walk-rest').addEventListener('click',() => { meshViewer?.rest(); $('walk-play').textContent = 'Play'; });
$('walk-time').addEventListener('input',() => { meshViewer?.seek(Number($('walk-time').value)); $('walk-play').textContent = 'Play'; });
$('walk-play-speed').addEventListener('change',() => meshViewer?.speed(Number($('walk-play-speed').value)));
$('walk-floor').addEventListener('change',() => meshViewer?.floor($('walk-floor').checked));
$('walk-follow').addEventListener('change',() => meshViewer?.follow($('walk-follow').checked));
$('create-walk').addEventListener('click',async () => {
  if (busy || !lastRigJob || !walkProfile?.supported || !$('walk-reviewed').checked) return;
  const source = lastRigJob;
  const paws = Object.fromEntries(['fore_left','fore_right','hind_left','hind_right'].map((r) => [r,$(`paw-${r}`).value]));
  const body = new URLSearchParams({profile:walkProfile.profile,paws:JSON.stringify(paws),reviewed:'true',speed:$('walk-speed').value,motion:$('walk-motion').value});
  busy = true; updateButton(); updateWalkControls(); updateRigControls(); updateConversionControls();
  configureStages(false,false,true);
  $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = true; });
  $('cancel').hidden = false; $('cancel').disabled = true;
  $('message').hidden = true; $('busy').hidden = false;
  generationStartedAt = Date.now();
  showProgress({stage:'starting',message:'Starting canine walking…'});
  const tick = setInterval(updateTiming,1000);
  try {
    const job = await request(`/api/jobs/${source}/walk`,{method:'POST',body});
    activeJobId = job.id; $('cancel').disabled = false;
    await disposeViewer(); await watchJob(job.id);
  } catch (error) { showError(error.message); $('result-info').textContent = 'Walking could not finish. The source rig is preserved.'; }
  finally {
    clearInterval(tick); busy = false; activeJobId = undefined;
    $('busy').hidden = true; $('cancel').hidden = true;
    $('form').querySelectorAll('input,select').forEach((input) => { input.disabled = false; });
    syncOutputControls(); updateButton(); updateWalkControls(); updateRigControls(); updateConversionControls();
  }
});
