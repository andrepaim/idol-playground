import './characters.css';

const $ = (id) => document.getElementById(id);
const labels = { pending: 'Not started', running: 'Working', awaiting_review: 'Needs review', succeeded: 'Reviewed', failed: 'Failed', cancelled: 'Stopped', interrupted: 'Interrupted', blocked: 'Blocked' };
let currentId, record, selectedFile, uploadIdentity, sourceUrl, sourceIdentity, imageKey, anatomyKey;
let busy = false, enabled = false, stopped = false, timer, selection = 0, artifactProblem = false;
let requests = new AbortController();
let imageDetailsReady = false, anatomyDetailsReady = true, viewEpoch = 0;

function message(text = '') {
  $('character-message').textContent = text;
  $('character-message').hidden = !text;
}

async function json(url, options = {}) {
  const response = await fetch(url, { cache: 'no-store', signal: requests.signal, ...options });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Check the image and review fields, then try again.');
    error.status = response.status;
    throw error;
  }
  return data;
}

function replaceSource(blob) {
  if (sourceUrl) URL.revokeObjectURL(sourceUrl);
  sourceUrl = blob ? URL.createObjectURL(blob) : undefined;
  if (sourceUrl) $('source-image').src = sourceUrl;
  else $('source-image').removeAttribute('src');
  $('source-image').hidden = !sourceUrl;
  $('source-empty').hidden = Boolean(sourceUrl);
}

function controls() {
  const running = Boolean(record && Object.values(record.stages).some((stage) => stage.state === 'running'));
  const unavailable = !enabled || record?.ready === false;
  for (const name of ['upload-fields', 'image-fields', 'anatomy-fields']) $(name).disabled = busy || running || unavailable;
  $('image-fields').disabled ||= !imageDetailsReady;
  $('anatomy-fields').disabled ||= !anatomyDetailsReady;
  $('upload-character').disabled = busy || running || unavailable || !selectedFile;
  $('confirm-image').disabled = busy || running || unavailable || !imageDetailsReady || !$('image-confirmed').checked;
  $('save-anatomy').disabled = busy || running || unavailable || !anatomyDetailsReady || !$('anatomy-confirmed').checked || $('body-plan').value === 'unknown';
  $('cancel-stage').hidden = !running;
  $('cancel-stage').disabled = busy || unavailable;
  $('retry-input').hidden = !record || (!artifactProblem && !['failed', 'cancelled', 'interrupted'].includes(record.stages.input.state));
  $('retry-input').disabled = busy || running || unavailable;
  $('saved-character').disabled = busy;
  $('new-character').disabled = busy || running;
  const whole = $('whole-image').checked;
  for (const name of ['crop-left', 'crop-top', 'crop-right', 'crop-bottom']) $(name).disabled = whole;
}

function badge(name, state) {
  $(name).textContent = labels[state] || 'Unavailable';
  $(name).dataset.state = state;
}

function artifact(stage, name) {
  return record?.stages[stage].artifacts.find((item) => item.name === name);
}

function artifactUrl(item) {
  const expected = `/api/characters/${currentId}/artifacts/`;
  const url = new URL(item.url, location.origin);
  if (url.origin !== location.origin || !url.pathname.startsWith(expected) || url.search || url.hash) throw new Error('The artifact link is invalid.');
  url.searchParams.set('revision', record.revision);
  return url.href;
}

function downloads() {
  $('character-downloads').replaceChildren();
  for (const [stage, name, label] of [['input', 'original.bin', 'Original image'], ['input', 'prepared.png', 'Prepared image'], ['assessment', 'assessment.json', 'Anatomy report']]) {
    const item = artifact(stage, name);
    if (!item) continue;
    const link = document.createElement('a');
    link.href = artifactUrl(item);
    link.textContent = label;
    link.download = name;
    $('character-downloads').append(link);
  }
}

async function originalImage(data) {
  const epoch = viewEpoch;
  const item = artifact('input', 'original.bin');
  if (!item || sourceIdentity === data.id) return;
  sourceIdentity = data.id;
  try {
    const response = await fetch(artifactUrl(item), { cache: 'no-store', signal: requests.signal });
    if (!response.ok) throw new Error('The original image could not be verified. Its saved files have been preserved.');
    const blob = await response.blob();
    if (currentId === data.id && epoch === viewEpoch && !stopped) replaceSource(blob);
  } catch (error) {
    if (!stopped && epoch === viewEpoch && currentId === data.id) message(error.message);
  }
}

async function reports(data) {
  const epoch = viewEpoch;
  const image = artifact('input', 'input.json');
  const nextImageKey = `${data.id}:${data.stages.input.attempt}:${data.stages.input.state}`;
  const assessment = artifact('assessment', 'assessment.json');
  const nextAnatomyKey = `${data.id}:${data.stages.assessment.attempt}:${data.stages.assessment.state}`;
  const loadImage = image && imageKey !== nextImageKey && data.stages.input.state !== 'running';
  const loadAnatomy = assessment && anatomyKey !== nextAnatomyKey && data.stages.assessment.state !== 'running';
  if (loadImage) { imageDetailsReady = false; imageKey = nextImageKey; }
  if (loadAnatomy) { anatomyDetailsReady = false; anatomyKey = nextAnatomyKey; }
  if (!assessment) anatomyDetailsReady = true;
  controls();
  if (loadImage) {
    try {
      const report = await json(artifactUrl(image));
      if (currentId !== data.id || epoch !== viewEpoch || imageKey !== nextImageKey) return;
      const crop = report.parameters.crop || [0, 0, report.source.width, report.source.height];
      $('whole-image').checked = report.parameters.crop === null;
      for (const [index, name] of ['crop-left', 'crop-top', 'crop-right', 'crop-bottom'].entries()) {
        $(name).value = crop[index];
        $(name).max = index % 2 ? report.source.height : report.source.width;
      }
      $('image-confirmed').checked = false;
      imageDetailsReady = true;
    } catch (error) {
      if (!stopped && epoch === viewEpoch && currentId === data.id) { artifactProblem = true; message(error.message); }
    }
  }
  if (loadAnatomy) {
    try {
      const report = await json(artifactUrl(assessment));
      if (currentId !== data.id || epoch !== viewEpoch || anatomyKey !== nextAnatomyKey) return;
      $('body-plan').value = report.body_plan;
      $('species').value = report.species;
      $('front-axis').value = report.front_axis;
      $('character-scale').value = report.scale_m;
      for (const [name, key] of [['single-subject', 'single_subject'], ['full-body', 'full_body'], ['limbs-separable', 'limbs_separable']]) $(name).checked = report[key];
      $('anatomy-confirmed').checked = false;
      anatomyDetailsReady = true;
      $('anatomy-note').textContent = report.body_plan === 'unsupported' ? 'This body plan is not supported yet. Your original image is preserved.' : data.stages.assessment.state === 'succeeded' ? 'Manual anatomy review saved. This does not yet validate a 3D rig or motion.' : 'Review the body plan and visibility. Uncertain or incomplete subjects remain under review.';
    } catch (error) {
      if (!stopped && epoch === viewEpoch && currentId === data.id) message(error.message);
    }
  }
  controls();
}

function render(data) {
  if (record?.id === data.id && data.revision < record.revision) return;
  record = data;
  badge('image-state', data.stages.input.state);
  badge('anatomy-state', data.stages.assessment.state);
  const prepared = artifact('input', 'prepared.png');
  $('prepared-image').hidden = !prepared;
  $('prepared-empty').hidden = Boolean(prepared);
  if (prepared) {
    const url = artifactUrl(prepared);
    if ($('prepared-image').src !== url) $('prepared-image').src = url;
  }
  $('image-review').hidden = !prepared;
  $('anatomy-panel').hidden = data.stages.input.state !== 'succeeded';
  downloads();
  controls();
  void originalImage(data);
  void reports(data);
  if (!data.ready) message('Processing needs local service recovery. Your saved files are preserved.');
}

function schedule() {
  clearTimeout(timer);
  if (currentId && !stopped) timer = setTimeout(refresh, 800);
}

async function refresh() {
  const identifier = currentId;
  const epoch = viewEpoch;
  if (!identifier || stopped) return;
  try {
    const data = await json(`/api/characters/${identifier}`);
    if (currentId !== identifier || epoch !== viewEpoch || stopped) return;
    $('connection-status').textContent = 'Connected to the local server';
    render(data);
  } catch (error) {
    if (currentId !== identifier || epoch !== viewEpoch || stopped) return;
    $('connection-status').textContent = 'Connection lost. Reconnecting…';
    if (error.status === 404) message('This character could not be found. Choose a saved character or upload a new image.');
  } finally {
    if (currentId === identifier && epoch === viewEpoch) schedule();
  }
}

async function savedCharacters() {
  const data = await json('/api/characters');
  const select = $('saved-character');
  select.replaceChildren(new Option('New character…', ''));
  data.characters.forEach((item, index) => {
    const state = item.error ? 'Needs repair' : labels[item.stages.assessment.state === 'succeeded' ? 'succeeded' : item.stages.input.state];
    select.add(new Option(`Character ${index + 1} · ${state}`, item.id));
  });
  select.value = currentId || '';
}

function address(identifier) {
  const url = new URL(location.href);
  if (identifier) url.searchParams.set('character', identifier);
  else url.searchParams.delete('character');
  history.replaceState(null, '', url);
}

function reset() {
  selection += 1; viewEpoch += 1;
  clearTimeout(timer);
  currentId = record = selectedFile = uploadIdentity = sourceIdentity = imageKey = anatomyKey = undefined;
  artifactProblem = false; imageDetailsReady = false; anatomyDetailsReady = true;
  $('image-review').reset(); $('anatomy-form').reset();
  $('character-image').value = '';
  $('saved-character').value = '';
  $('anatomy-note').textContent = '';
  $('image-review').hidden = $('anatomy-panel').hidden = true;
  $('prepared-image').hidden = true;
  $('prepared-image').removeAttribute('src');
  $('prepared-empty').hidden = false;
  $('character-downloads').replaceChildren();
  replaceSource(null);
  badge('image-state', 'pending'); badge('anatomy-state', 'pending');
  address(null);
  message();
  controls();
}

async function open(identifier) {
  reset();
  if (!identifier) return;
  currentId = identifier;
  address(identifier);
  $('saved-character').value = identifier;
  await refresh();
}

async function operation(action) {
  if (busy) return;
  busy = true; message(); controls();
  try { await action(); }
  catch (error) { if (!stopped) message(error.message); }
  finally { busy = false; controls(); }
}

function imageSettings() {
  let crop = null;
  if (!$('whole-image').checked) {
    crop = ['crop-left', 'crop-top', 'crop-right', 'crop-bottom'].map((name) => Number($(name).value));
    if (!crop.every(Number.isInteger) || crop[0] < 0 || crop[1] < 0 || crop[2] - crop[0] < 16 || crop[3] - crop[1] < 16) throw new Error('Choose a crop inside the image, at least 16 pixels wide and high.');
  }
  return { confirmed: $('image-confirmed').checked, crop };
}

$('character-image').addEventListener('change', async () => {
  const file = $('character-image').files[0];
  if (!file) return;
  const epoch = ++selection;
  selectedFile = uploadIdentity = undefined; controls();
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 20 * 1024 * 1024) { message('Choose a PNG, JPEG or WebP image up to 20 MiB.'); return; }
  let bytes;
  try { bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer()); }
  catch { message('The selected file could not be read. Choose it again.'); return; }
  if (epoch !== selection || stopped) return;
  const png = [137, 80, 78, 71, 13, 10, 26, 10].every((value, index) => bytes[index] === value);
  const jpeg = bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
  const webp = String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF' && String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP';
  if (!png && !jpeg && !webp) { message('This file does not appear to contain a supported image.'); return; }
  reset();
  selectedFile = file;
  uploadIdentity = crypto.randomUUID().replaceAll('-', '');
  replaceSource(file);
  controls();
});

$('character-upload').addEventListener('submit', (event) => {
  event.preventDefault();
  if (!selectedFile) return;
  void operation(async () => {
    const form = new FormData(); form.set('request_id', uploadIdentity); form.set('image', selectedFile);
    let data;
    try { data = await json('/api/characters', { method: 'POST', body: form }); }
    catch (error) {
      if (!error.status || error.status >= 500 || error.status === 409) {
        try { data = await json(`/api/characters/${uploadIdentity}`); } catch { throw error; }
      } else throw error;
    }
    selectedFile = undefined; $('character-image').value = '';
    currentId = data.id; address(currentId); render(data); schedule();
    await savedCharacters();
  });
});

$('image-review').addEventListener('submit', (event) => {
  event.preventDefault();
  void operation(async () => {
    const data = await json(`/api/characters/${currentId}/input`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(imageSettings()) });
    artifactProblem = false; render(data); schedule();
  });
});

$('anatomy-form').addEventListener('submit', (event) => {
  event.preventDefault();
  void operation(async () => {
    const settings = { body_plan: $('body-plan').value, species: $('species').value, front_axis: $('front-axis').value, scale_m: Number($('character-scale').value), single_subject: $('single-subject').checked, full_body: $('full-body').checked, limbs_separable: $('limbs-separable').checked, confirmed: $('anatomy-confirmed').checked };
    const data = await json(`/api/characters/${currentId}/assessment`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) });
    render(data); schedule();
  });
});

$('cancel-stage').addEventListener('click', () => void operation(async () => { render(await json(`/api/characters/${currentId}/cancel`, { method: 'POST' })); schedule(); }));
$('retry-input').addEventListener('click', () => void operation(async () => { artifactProblem = false; $('prepared-image').removeAttribute('src'); render(await json(`/api/characters/${currentId}/stages/input/retry`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(imageSettings()) })); schedule(); }));
$('new-character').addEventListener('click', () => { reset(); $('saved-character').value = ''; });
$('saved-character').addEventListener('change', () => void open($('saved-character').value));
for (const name of ['image-confirmed', 'anatomy-confirmed']) $(name).addEventListener('change', controls);
for (const name of ['whole-image', 'crop-left', 'crop-top', 'crop-right', 'crop-bottom']) $(name).addEventListener('change', () => { $('image-confirmed').checked = false; controls(); });
for (const name of ['body-plan', 'species', 'front-axis', 'character-scale', 'single-subject', 'full-body', 'limbs-separable']) $(name).addEventListener('change', () => { $('anatomy-confirmed').checked = false; controls(); });
$('prepared-image').addEventListener('error', () => { artifactProblem = true; message('The prepared image could not be verified. Retry preparation; your original is preserved.'); controls(); });

function cleanup() { stopped = true; viewEpoch += 1; selection += 1; clearTimeout(timer); requests.abort(); replaceSource(null); }
window.addEventListener('pagehide', cleanup);
window.addEventListener('pageshow', (event) => { if (event.persisted) { stopped = false; requests = new AbortController(); sourceIdentity = undefined; if (currentId) void refresh(); else if (selectedFile) replaceSource(selectedFile); controls(); } });

async function bootstrap() {
  try {
    const status = await json('/api/status');
    enabled = Boolean(status.characters?.enabled);
    $('disabled-notice').hidden = enabled;
    $('workflow').hidden = !enabled;
    $('connection-status').textContent = enabled ? 'Connected to the local server' : 'Character preparation is unavailable on this server';
    controls();
    if (!enabled) return;
    await savedCharacters();
    const identifier = new URL(location.href).searchParams.get('character');
    if (identifier && !/^[0-9a-f]{32}$/.test(identifier)) message('Invalid character link. Choose a saved character or upload a new image.');
    else if (identifier) await open(identifier);
  } catch { $('connection-status').textContent = 'Connection lost. Reload to reconnect.'; }
}
void bootstrap();
