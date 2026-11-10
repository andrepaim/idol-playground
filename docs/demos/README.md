# Paçoca turntable demonstration

The repository owner requested a public README demonstration using their `pacoca.jpg` photograph. The photo shows Paçoca sitting outdoors. Only the reviewed app recording is included; the original image file and its metadata, model weights, generated PLY, private job identifiers, and raw capture frames stay outside Git.

## Generation

The original photograph was uploaded through the actual local interface. Idol ran on the RTX 3060 at application revision `a8190c0c50bb377a12c32bfa2f2d320793acbaf4` with the pinned model sources in `model_setup.py`.

| Setting | Value |
|---|---|
| Image type | Real photograph |
| Sampling steps | 50 |
| Gaussians | 262,144 |
| Seed | 42 |
| Guidance | 3 |
| Time shift | 3 |
| Server generation time | 154.0 seconds |

The media shows the actual completed reconstruction, including inferred surfaces. It does not establish the shape of unseen anatomy or animation/game readiness.

## Capture and files

- [Looping README preview](pacoca-turntable.gif).
- [MP4 video](pacoca-turntable.mp4?raw=1).

The capture reconnects the interface to the completed real job and uses its full, unmodified PLY. Camera framing is zoomed in and a full 360° orbit is automated through the existing viewer. The normal renderer captures 228 browser frames at 1360 × 1100, encoded at 24 fps for a 9.5-second turntable with a short hold at each end. This is a frame-by-frame turntable recording, not a real-time inference-speed demonstration. No production application code is changed.

The MP4 uses H.264, 1280-pixel width, yuv420p, no audio, and fast-start metadata. The compact GIF is resized to 960 pixels wide at 10 fps and loops indefinitely. Browser chrome, desktop files, original EXIF, and local paths are absent.

Validation includes visual review of the original photo and capture at several angles, full media decode, frame/duration checks, local links/whitespace, and repository security checks. Exact approved file hashes and provenance are recorded in `security/reviewed-assets.json` at the repository root. Approval applies only to these owner-requested demonstration files, not to other images or generated outputs.

| File | Dimensions | Frame rate | Duration | Bytes |
|---|---|---|---|---:|
| MP4 | 1280 × 1036 | 24 fps | 9.5 s | 325,439 |
| GIF | 960 × 776 | 10 fps | 9.5 s | 1,340,439 |
