"""One isolated UniRig phase. No shell wrappers, network access or cloud logging."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import time
import traceback


def extract(file):
    from src.data.extract import clean_bpy, load, get_arranged_bones, process_mesh, process_armature, save_raw_data
    clean_bpy()
    armature = load(str(file))
    bones = get_arranged_bones(armature) if armature is not None else None
    vertices, faces, skin = process_mesh(bones)
    joints, tails, parents, names, matrix = process_armature(armature, bones) if bones is not None else (None,) * 5
    output = file.with_suffix('') / 'raw_data.npz'
    output.parent.mkdir(exist_ok=True)
    save_raw_data(path=str(output), vertices=vertices, faces=faces-1, skin=skin, joints=joints,
                  tails=tails, parents=parents, names=names, matrix_local=matrix, target_count=50000)
    if not output.is_file():raise RuntimeError('Mesh preparation did not produce geometry')


def predict(args, kind):
    import torch
    from transformers import AutoConfig
    import src.inference.download as downloads
    torch.set_num_threads(4)
    if not torch.cuda.is_available():raise RuntimeError('CUDA is unavailable in the rigging environment')
    torch.cuda.reset_peak_memory_stats()
    original = AutoConfig.from_pretrained
    def local_config(*values, **kwargs):
        name = kwargs.pop('pretrained_model_name_or_path', values[0] if values else None)
        if name != 'facebook/opt-350m':raise ValueError('Unexpected rig model dependency')
        return original(str(args.models / 'unirig-opt'), local_files_only=True, **kwargs)
    AutoConfig.from_pretrained = local_config
    def local_download(path):
        file = args.models / 'unirig' / path.removeprefix('experiments/')
        if not file.is_file():raise RuntimeError('Rigging weights are missing; run make rig-models')
        return str(file)
    downloads.download = local_download
    if kind == 'skeleton':
        task, input_name, output_name = 'quick_inference_skeleton_articulationxl_ar_256', 'input.glb', 'skeleton.fbx'
    else:
        task, input_name, output_name = 'quick_inference_unirig_skin', 'skeleton.fbx', 'skin.fbx'
    sys.argv = ['run.py', '--task=configs/task/' + task + '.yaml', '--seed=' + str(args.seed),
                '--input=' + str(args.job / input_name), '--output=' + str(args.job / output_name),
                '--npz_dir=' + str(args.job), '--data_name=raw_data.npz']
    # Disable Lightning's default logger too; no local or cloud training logs are needed.
    import lightning
    trainer = lightning.Trainer
    class LocalTrainer(trainer):
        def __init__(self, *values, **kwargs):
            kwargs['logger'] = False
            kwargs['enable_progress_bar'] = False
            super().__init__(*values, **kwargs)
    lightning.Trainer = LocalTrainer
    runpy.run_path(str(args.models / 'unirig-source/run.py'), run_name='__main__')
    result = args.job / output_name
    if not result.is_file() or result.stat().st_size < 1000:
        raise RuntimeError('Rig model did not produce its expected export')
    (args.job / (kind + '-stats.json')).write_text(json.dumps({
        'peak_allocated_mib': round(torch.cuda.max_memory_allocated() / 2**20),
        'gpu': torch.cuda.get_device_name(0), 'torch': torch.__version__}))


def scene_report():
    import bpy
    import numpy as np
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE']
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH'
              and any(not collection.hide_render for collection in obj.users_collection)]
    if len(armatures) != 1 or not meshes:raise ValueError('Export has no unique character armature/mesh')
    armature = armatures[0]
    bones = set(armature.data.bones.keys())
    if len(bones) < 2:raise ValueError('Export has no usable skeleton')
    vertices = 0
    colored = 0
    color_sum = np.zeros(3)
    color_count = 0
    for mesh in meshes:
        if not any(mod.type == 'ARMATURE' and mod.object == armature for mod in mesh.modifiers):
            raise ValueError('Mesh is not bound to its skeleton')
        for vertex in mesh.data.vertices:
            weights = [group.weight for group in vertex.groups if mesh.vertex_groups[group.group].name in bones and group.weight > 0]
            if not weights or len(weights) > 4 or not np.isfinite(weights).all() or abs(sum(weights)-1) > .002:
                raise ValueError('Export has invalid skin weights')
        vertices += len(mesh.data.vertices)
        attribute = mesh.data.color_attributes.active_color
        if attribute is not None:
            values = np.empty(len(attribute.data)*4,dtype=np.float32)
            attribute.data.foreach_get('color',values)
            values = values.reshape(-1,4)
            if not len(values) or not np.isfinite(values).all() or values.min() < 0 or values.max() > 1.001:
                raise ValueError('Export has invalid vertex colors')
            if attribute.domain == 'POINT':
                indices = np.empty(len(mesh.data.loops),dtype=np.int32)
                mesh.data.loops.foreach_get('vertex_index',indices)
                values = values[indices]
            color_sum += values[:,:3].sum(axis=0,dtype=np.float64)
            color_count += len(values)
            colored += 1
    images = set()
    for mesh in meshes:
        for material in mesh.data.materials:
            if not material or not material.use_nodes:continue
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    image = node.image
                    if len(image.pixels) == 0 or min(image.size) <= 0:
                        raise ValueError('Export has an unreadable texture')
                    images.add(image.name)
    return {'bones': len(bones), 'vertices': vertices, 'materials': len(bpy.data.materials), 'images': len(images),
            'vertex_color_meshes': colored,'color_mean': (color_sum/max(color_count,1)).tolist()}


def export(args):
    import bpy
    import numpy as np
    from src.inference.merge import transfer
    transfer(str(args.job / 'skin.fbx'), str(args.job / 'input.glb'), str(args.job / 'rigged.glb'))
    original_appearance = scene_report()
    armature = next(obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE')
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH'
              and any(not collection.hide_render for collection in obj.users_collection)]
    def evaluated():
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        points = []
        for mesh in meshes:
            current = mesh.evaluated_get(depsgraph)
            data = current.to_mesh()
            points.extend([current.matrix_world @ vertex.co for vertex in data.vertices])
            current.to_mesh_clear()
        return np.asarray(points)
    before = evaluated()
    counts = {}
    for mesh in meshes:
        for vertex in mesh.data.vertices:
            for group in vertex.groups:
                if group.weight > .05:
                    name = mesh.vertex_groups[group.group].name
                    counts[name] = counts.get(name, 0) + 1
    candidates = [bone for bone in armature.pose.bones if bone.parent and .01*len(before) < counts.get(bone.name, 0) < .5*len(before)]
    if not candidates:raise ValueError('No independently weighted bone can be tested')
    bone = max(candidates, key=lambda item: counts[item.name])
    bone.rotation_mode = 'XYZ'
    bone.rotation_euler = (0,0,0)
    bone.keyframe_insert(data_path='rotation_euler', frame=1)
    bone.rotation_euler.x = .25
    bone.keyframe_insert(data_path='rotation_euler', frame=16)
    displacement = np.linalg.norm(evaluated()-before, axis=1)
    if not np.isfinite(displacement).all() or displacement.max() < 1e-5:
        raise ValueError('Weighted vertices did not move during the diagnostic bend')
    bone.rotation_euler.x = 0
    bone.keyframe_insert(data_path='rotation_euler', frame=31)
    armature.animation_data.action.name = 'Diagnostic bend'
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 31
    bpy.context.scene.render.fps = 24
    bpy.context.scene.frame_set(1)
    bpy.ops.export_scene.gltf(filepath=str(args.job / 'rigged.glb'), export_format='GLB',
                              export_animations=True, export_frame_range=True, export_force_sampling=True)
    # Give FBX's embedded-image writer real local files, and pack them into Blend.
    texture_dir = args.job / 'rig-textures'
    texture_dir.mkdir(exist_ok=True)
    for index, image in enumerate(bpy.data.images):
        if image.type != 'IMAGE' or not image.has_data:continue
        image.filepath_raw = str(texture_dir / f'texture-{index}.png')
        image.file_format = 'PNG'
        image.save()
    bpy.ops.export_scene.fbx(filepath=str(args.job / 'rigged.fbx'), add_leaf_bones=False,
                             path_mode='COPY', embed_textures=True, bake_anim=True,
                             bake_anim_use_all_actions=False)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.job / 'character.blend'))
    report = {'backend': 'unirig', 'rigged': True, 'source_appearance': original_appearance,
              'appearance': 'vertex_colors' if original_appearance['vertex_color_meshes'] else 'texture', 'diagnostic_bone': bone.name,
              'deformation_max': float(displacement.max()), 'deformed_vertices': int((displacement > 1e-5).sum()),
              'warnings': ['Experimental automatic rig. Inspect bone placement and deformation before game use.',
                           'Generic bone names; engine retargeting and authored animations are separate steps.']}
    if report['appearance'] == 'vertex_colors':
        report['warnings'].append('FBX preserves vertex-color data; configure a material that uses those colors in your engine.')
    for stage in ('skeleton', 'skinning'):
        report[stage] = json.loads((args.job / (stage + '-stats.json')).read_text())
    (args.job / 'rig.json').write_text(json.dumps(report, indent=2))


def verify(args):
    import bpy
    from src.data.extract import clean_bpy, load
    reports = {}
    for name in ('rigged.glb', 'rigged.fbx'):
        clean_bpy();load(str(args.job / name))
        reports[name] = scene_report()
    bpy.ops.wm.open_mainfile(filepath=str(args.job / 'character.blend'), load_ui=False, use_scripts=False)
    reports['character.blend'] = scene_report()
    report = json.loads((args.job / 'rig.json').read_text())
    if report.get('appearance') == 'vertex_colors':
        import numpy as np
        expected = report['source_appearance']['color_mean']
        for name,item in reports.items():
            if item['vertex_color_meshes'] < 1 or np.max(np.abs(np.asarray(item['color_mean'])-expected)) > .02:
                raise ValueError('A character export lost or changed its vertex colors: '+name)
    elif any(item['images'] < 1 for item in reports.values()):raise ValueError('A character export lost its texture')
    if len({item['bones'] for item in reports.values()}) != 1:raise ValueError('Skeleton changed during export round trip')
    report = json.loads((args.job / 'rig.json').read_text())
    report['roundtrips'] = reports
    (args.job / 'rig.json').write_text(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', required=True, choices=('rig_prepare','skeleton','rig_bind','skinning','rig_export','rig_verify'))
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    args.models = args.models.resolve();args.job = args.job.resolve()
    source = args.models / 'unirig-source'
    sys.path.insert(0, str(source));os.chdir(args.job)
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',WANDB_MODE='disabled',WANDB_DISABLED='true',OMP_NUM_THREADS='4')
    started = time.monotonic()
    if args.phase == 'rig_prepare':extract(args.job / 'input.glb')
    elif args.phase == 'rig_bind':extract(args.job / 'skeleton.fbx')
    elif args.phase in ('skeleton','skinning'):
        # Upstream configuration paths are relative to its source tree.
        os.chdir(source);predict(args, args.phase)
    elif args.phase == 'rig_export':export(args)
    else:verify(args)
    print('IDOL_EVENT ' + json.dumps({'event':'phase_complete','phase':args.phase,'seconds':round(time.monotonic()-started,3)}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        traceback.print_exc(file=sys.stderr)
        message = str(error)
        if 'out of memory' in message.lower():message = 'GPU ran out of memory during rigging. Close other GPU apps and retry.'
        print('IDOL_EVENT '+json.dumps({'event':'error','message':message[:1000]}),flush=True)
        code = 1
    else:code = 0
    # bpy 4.2 can crash while destroying native state on WSL interpreter teardown.
    # Every operation and explicit result check has finished; errors above stay failures.
    sys.stdout.flush();sys.stderr.flush();os._exit(code)
