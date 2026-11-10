"""One TripoSR job in an isolated CUDA environment. Stdout carries bounded JSON events."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback


def emit(stage, message, **details):
    print('IDOL_EVENT ' + json.dumps({'event': 'progress', 'stage': stage, 'message': message, **details}), flush=True)


def run(args):
    os.environ.setdefault('OMP_NUM_THREADS', '4')
    os.environ['U2NET_HOME'] = str(args.models / 'rembg')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    sys.path.insert(0, str(args.models / 'triposr-source'))
    import numpy as np
    from PIL import Image, ImageOps
    import torch
    import rembg
    import trimesh
    from surface_export import textured_mesh
    from omegaconf import OmegaConf
    from tsr.system import TSR
    from tsr.models.tokenizers import image as image_tokenizer
    from tsr.utils import resize_foreground
    from tsr import bake_texture as baking
    import moderngl

    def local_encoder(*, repo_id, filename, **kwargs):
        if repo_id != 'facebook/dino-vitb16' or filename != 'config.json':
            raise RuntimeError('Unexpected encoder dependency; rerun model setup.')
        return str(args.models / 'triposr-dino/config.json')

    image_tokenizer.hf_hub_download = local_encoder
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable in the mesh environment. Check setup-mesh and nvidia-smi.')
    torch.set_num_threads(4)
    settings = json.loads(args.settings.read_text())
    resolution, texture_size, target_faces = (settings['mesh_resolution'], settings['texture_resolution'], settings['target_faces'])
    if resolution not in (128, 192, 256) or texture_size not in (512, 1024, 2048) or target_faces not in (10000, 25000, 50000, 100000):
        raise ValueError('Unsupported mesh settings')
    args.output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(settings.get('seed', 42))
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    emit('preprocess', 'Removing the background and framing the subject…')
    image = ImageOps.exif_transpose(Image.open(args.input)).convert('RGBA')
    image.thumbnail((2048, 2048))
    if image.getextrema()[3][0] == 255:
        session = rembg.new_session('u2net', providers=['CPUExecutionProvider'])
        image = rembg.remove(image, session=session)
    if image.getchannel('A').getbbox() is None:
        raise ValueError('No foreground subject was found. Try a clearer image.')
    image = resize_foreground(image, 0.85)
    image.save(args.output / 'prepared.png')
    rgba = np.asarray(image).astype(np.float32) / 255
    rgb = rgba[..., :3] * rgba[..., 3:] + (1 - rgba[..., 3:]) * .5
    image = Image.fromarray(np.uint8(np.clip(rgb * 255, 0, 255)))
    emit('load', 'Loading the mesh reconstruction model onto your GPU…')
    config = OmegaConf.load(args.models / 'triposr/config.yaml')
    OmegaConf.resolve(config)
    model = TSR(config)
    state = torch.load(args.models / 'triposr/model.ckpt', map_location='cpu', weights_only=True)
    model.load_state_dict(state)
    del state
    model.renderer.set_chunk_size(8192)
    model.to('cuda').eval()
    emit('reconstruct', 'Reconstructing the subject’s shape and appearance…')
    with torch.inference_mode():
        codes = model([image], device='cuda')
    torch.cuda.synchronize()
    emit('extract', 'Extracting the triangle surface…', step=0, total_steps=resolution**3)
    completed = 0
    last_emit = 0

    def field_progress(module, inputs, output):
        nonlocal completed, last_emit
        completed += len(inputs[0])
        now = time.monotonic()
        if now - last_emit > .5:
            torch.cuda.synchronize()
            emit('extract', 'Evaluating the surface density…', step=min(completed, resolution**3), total_steps=resolution**3)
            last_emit = now

    hook = model.decoder.register_forward_hook(field_progress)
    try:
        with torch.inference_mode():
            mesh = model.extract_mesh(codes, has_vertex_color=True, resolution=resolution)[0]
    finally:
        hook.remove()
    if len(mesh.faces) < 4:
        raise ValueError('No usable surface was reconstructed. Try a clearer subject.')
    # Preserve the reconstruction before topology changes. This artifact stays local.
    mesh.export(args.output / 'source-mesh.glb')
    raw_faces = len(mesh.faces)
    emit('simplify', 'Cleaning geometry and reducing the triangle count…')
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces) > target_faces:
        mesh = mesh.simplify_quadric_decimation(face_count=target_faces)
    mesh.fix_normals()
    if not np.isfinite(mesh.vertices).all() or not len(mesh.faces):
        raise ValueError('Reconstructed geometry is invalid')
    components = len(trimesh.graph.connected_components(mesh.face_adjacency, nodes=np.arange(len(mesh.faces)), min_len=1))
    emit('texture', 'Unwrapping the mesh and baking its appearance…')
    atlas = baking.make_atlas(mesh, texture_size, max(2, texture_size // 256))
    original_context = moderngl.create_context

    def offscreen_context(*args_, **kwargs):
        kwargs.setdefault('backend', 'egl')
        return original_context(*args_, **kwargs)

    moderngl.create_context = offscreen_context
    positions = baking.rasterize_position_atlas(mesh, atlas['vmapping'], atlas['indices'], atlas['uvs'],
                                               texture_size, max(2, texture_size // 256))
    flat = positions.reshape(-1, 4)
    valid = np.flatnonzero(flat[:, 3] > 0)
    colors = np.zeros((len(flat), 4), dtype=np.uint8)
    for offset in range(0, len(valid), 8192):
        ids = valid[offset:offset + 8192]
        points = torch.from_numpy(flat[ids, :3].copy()).to('cuda')
        with torch.inference_mode():
            color = model.renderer.query_triplane(model.decoder, points, codes[0])['color']
        colors[ids, :3] = np.uint8(np.clip(color.cpu().numpy() * 255, 0, 255))
        colors[ids, 3] = 255
        if offset % (8192 * 16) == 0 or offset + 8192 >= len(valid):
            emit('texture', 'Baking the color texture…', step=min(offset + 8192, len(valid)), total_steps=len(valid))
    texture = Image.fromarray(colors.reshape(texture_size, texture_size, 4)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    texture.save(args.output / 'texture.png')
    final = textured_mesh(mesh, atlas, texture)
    # TripoSR uses Z-up; glTF and the mesh viewer use Y-up. Bake before rotating.
    final.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
    emit('export', 'Embedding textures and saving the GLB…')
    final.export(args.output / 'object.glb', include_normals=True)
    roundtrip = trimesh.load(args.output / 'object.glb', force='scene', process=False)
    if not len(roundtrip.geometry):
        raise ValueError('Exported GLB could not be reloaded')
    report = {'backend': 'triposr', 'triangles': len(final.faces), 'vertices': len(final.vertices),
              'source_triangles': raw_faces, 'texture_resolution': texture_size, 'components': components,
              'watertight': bool(mesh.is_watertight), 'rigged': False, 'up_axis': 'Y',
              'bounds': final.bounds.tolist(), 'seconds': round(time.monotonic() - started, 2),
              'gpu': torch.cuda.get_device_name(0), 'peak_allocated_mib': round(torch.cuda.max_memory_allocated() / 2**20),
              'surface_extraction': 'CPU marching cubes (PyMCubes)',
              'warnings': ['Single-image reconstruction; inspect anatomy and topology before rigging.']}
    (args.output / 'mesh.json').write_text(json.dumps(report, indent=2))
    print('IDOL_EVENT ' + json.dumps({'event': 'complete', 'mesh': report}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--settings', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        message = str(error)
        if 'out of memory' in message.lower():
            message = 'GPU ran out of memory. Use a smaller surface resolution and close other GPU apps.'
        print('IDOL_EVENT ' + json.dumps({'event': 'error', 'message': message[:1000]}), flush=True)
        raise SystemExit(1)
