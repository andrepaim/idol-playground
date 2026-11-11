# Playable canine sample

This private local export includes the selected in-place character and a reusable Three.js scene. It needs no inference backend, API credentials or reasoning service.

1. Install Node matching the authoring repository's `.node-version` (copied into this archive).
2. Run `npm ci` in this folder. Initial installation needs access to npm unless dependencies are cached.
3. Run `python3 -m http.server 8080 --bind 127.0.0.1` (or any local static HTTP server).
4. Open `http://127.0.0.1:8080` in a desktop WebGL2 browser. After dependency installation the scene works without external network access. Opening the HTML through `file://` is unsupported.

Click the scene, then use WASD or arrow keys. Drag to orbit, scroll to zoom, and reset with the button. Leaving the scene clears input. The controller uses an in-place walking clip, a standing hold, conservative collision, a flat floor and simple obstacles. It assumes two-metre horizontal extent and the reviewed canine profile; this is not certification of anatomical quality or natural movement.

`character.json` has the profile, movement mode, stride, artifact hash and current limitations. Original images, source-job identifiers, absolute paths, logs and credentials are excluded.

Dependencies: Three.js 0.187.0, installed from the locked npm package under its included MIT license at `node_modules/three/LICENSE`. Runtime source is copied from Idol Playground; this export grants no additional source-code or character redistribution rights. Character/input/model-derived asset rights remain those of their respective sources. This download is for local use; review those terms before redistribution.
