// Records one full orbit of the current preview as a video, in the browser, from the viewer's own canvas.
const FORMATS = [
  ['video/mp4;codecs=avc1', 'mp4'],
  ['video/mp4', 'mp4'],
  ['video/webm;codecs=vp9', 'webm'],
  ['video/webm', 'webm'],
];

export function videoFormat() {
  if (typeof MediaRecorder === 'undefined' || !HTMLCanvasElement.prototype.captureStream) return undefined;
  const found = FORMATS.find(([type]) => MediaRecorder.isTypeSupported(type));
  return found && { type: found[0], extension: found[1] };
}

const nextFrame = () => new Promise((resolve) => requestAnimationFrame(resolve));

// orbit: { camera, controls, render() }. The camera turns once around controls.target about camera.up,
// then returns to where it started, so the user's view is unchanged afterwards.
//
// A WebGL canvas is not recorded directly: without preserveDrawingBuffer, captureStream can deliver no new frames
// (headless Chromium records one). Each rendered frame is copied, during the frame that drew it, onto an opaque 2D
// canvas, and that canvas is recorded with one explicitly requested video frame per copy.
export async function recordTurntable(source, orbit, { seconds = 8, fps = 30, background = '#111713', onProgress } = {}) {
  const format = videoFormat();
  if (!format) throw new Error('This browser cannot record video from the preview.');
  const { camera, controls } = orbit;
  const start = camera.position.clone();
  const offset = start.clone().sub(controls.target);
  const axis = camera.up.clone().normalize();
  const enabled = controls.enabled;
  const frame = document.createElement('canvas');
  frame.width = source.width - (source.width % 2);
  frame.height = source.height - (source.height % 2);
  const context = frame.getContext('2d');
  const stream = frame.captureStream(0);
  const [track] = stream.getVideoTracks();
  const recorder = new MediaRecorder(stream, { mimeType: format.type, videoBitsPerSecond: 8_000_000 });
  const chunks = [];
  recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
  const stopped = new Promise((resolve, reject) => {
    recorder.onstop = resolve;
    recorder.onerror = (event) => reject(event.error || new Error('Video recording failed.'));
  });
  const place = (angle) => {
    camera.position.copy(controls.target).add(offset.clone().applyAxisAngle(axis, angle));
    camera.lookAt(controls.target);
    controls.update();
    orbit.render();
  };
  const capture = () => {
    context.fillStyle = background;
    context.fillRect(0, 0, frame.width, frame.height);
    context.drawImage(source, 0, 0, frame.width, frame.height, 0, 0, frame.width, frame.height);
    track.requestFrame();
  };
  const total = Math.round(seconds * fps);
  controls.enabled = false;
  try {
    place(0);
    await nextFrame();
    recorder.start();
    // The viewer renders in its own animation-frame callback, registered before this one, so each callback here
    // copies the frame just drawn for the previous angle, then sets the next angle, paced to the target frame rate.
    const began = performance.now();
    for (let index = 0; index <= total; index++) {
      while (performance.now() - began < (index * 1000) / fps) await nextFrame();
      await nextFrame();
      capture();
      onProgress?.(index / total);
      if (index < total) place(((index + 1) / total) * Math.PI * 2);
    }
    recorder.stop();
    await stopped;
  } finally {
    if (recorder.state !== 'inactive') recorder.stop();
    track.stop();
    camera.position.copy(start);
    camera.lookAt(controls.target);
    controls.update();
    controls.enabled = enabled;
    orbit.render();
  }
  return { blob: new Blob(chunks, { type: format.type.split(';')[0] }), extension: format.extension };
}
