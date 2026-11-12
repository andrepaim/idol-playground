"""Template-skeleton vertical slice (issue #72), run inside the official Blender 4.2 executable:

    blender --background --factory-startup --python-exit-code 1 \
        --python experiments/vertical_slice/slice_blender.py -- \
        --repo . --fox Fox.glb --mesh object.glb --out OUTDIR [--target-triangles 48000]

Dense vertex-colored mesh -> simplified game mesh -> canonical frame -> Fox 24-joint quadruped template
fitted from geometric landmarks -> heat-weight skinning -> Fox Walk retargeted through rest-relative
world rotations -> in-place GLB plus a JSON receipt of every measurement. Experiment tooling only.
"""
import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True)
parser.add_argument('--fox', required=True)
parser.add_argument('--mesh', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--target-triangles', type=int, default=48000)
parser.add_argument('--skip-silhouettes', action='store_true')
parser.add_argument('--gait', choices=['fox', 'procedural'], default='fox',
                    help='paw contact timing: the authored Fox clip, or a 4-beat lateral-sequence dog walk')
parser.add_argument('--body-motion', type=float, default=1.0,
                    help='fraction of the Fox spine/neck/head/hip motion to keep (1 = faithful retarget)')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
sys.path.insert(0, os.path.abspath(args.repo))
from experiments.vertical_slice import quadruped_fit as qf  # noqa: E402

os.makedirs(args.out, exist_ok=False)
receipt = {'schema': 'vertical-slice-a-v1', 'blender': bpy.app.version_string, 'python': platform.python_version(),
           'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'settings': vars(args), 'phases': {}}
started = time.perf_counter()


def phase(name):
    now = time.perf_counter()
    receipt['phases'][name] = round(now - phase.last, 3)
    phase.last = now
    save()


phase.last = started


def save():
    with open(os.path.join(args.out, 'receipt.json'), 'w') as handle:
        json.dump(receipt, handle, indent=2, default=lambda v: list(v) if hasattr(v, '__iter__') else str(v))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def mesh_arrays(obj):
    me = obj.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    me.calc_loop_triangles()
    tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get('vertices', tris)
    world = np.array(obj.matrix_world)
    co = co.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]
    return co, tris.reshape(-1, 3)


def mean_color(obj):
    attribute = obj.data.color_attributes.active_color
    values = np.empty(len(attribute.data) * 4)
    attribute.data.foreach_get('color', values)
    return values.reshape(-1, 4)[:, :3].mean(0).round(4).tolist(), attribute.domain


def activate(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def linear_keys(owner):
    if owner.animation_data and owner.animation_data.action:
        for curve in owner.animation_data.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = 'LINEAR'


receipt['inputs'] = {'fox_sha256': sha256(args.fox), 'mesh_sha256': sha256(args.mesh)}
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---- 1. Dense mesh -> simplified game mesh -------------------------------------------------------------
bpy.ops.import_scene.gltf(filepath=args.mesh)
target = next(o for o in scene.objects if o.type == 'MESH')
activate(target)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
dense = target.copy()
dense.data = target.data.copy()
dense.name = 'Dense'
scene.collection.objects.link(dense)
dense_points, dense_tris = mesh_arrays(dense)
mod = target.modifiers.new('decimate', 'DECIMATE')
mod.decimate_type = 'COLLAPSE'
mod.ratio = args.target_triangles / len(dense_tris)
mod.use_collapse_triangulate = True
activate(target)
bpy.ops.object.modifier_apply(modifier=mod.name)
target.name = 'Character'
points, tris = mesh_arrays(target)
receipt['mesh'] = {'dense_vertices': len(dense_points), 'dense_triangles': len(dense_tris),
                   'prepared_vertices': len(points), 'prepared_triangles': len(tris),
                   'decimate_ratio': args.target_triangles / len(dense_tris),
                   'dense_mean_rgb': mean_color(dense), 'prepared_mean_rgb': mean_color(target)}
phase('simplify')

# ---- 2. Canonical frame (Fox convention: +Z up, head -Y, left +X, floor 0) --------------------------------
matrix, orientation = qf.canonicalize(points.tolist())
canonical = Matrix(matrix)
target.data.transform(canonical)
dense.data.transform(canonical)
points, tris = mesh_arrays(target)
diag = float(np.linalg.norm(points.max(0) - points.min(0)))
receipt['canonical'] = {'orientation': orientation, 'bbox_min': points.min(0).tolist(),
                        'bbox_max': points.max(0).tolist(), 'L_diagonal': diag,
                        'note': 'Head direction is a geometric heuristic; confirm in the review renders.'}

# ---- 3. Silhouette agreement dense vs prepared (8 orthographic views, Cycles alpha) -----------------------
material = bpy.data.materials.new('VertexColor')
material.use_nodes = True
nodes = material.node_tree.nodes
attribute_node = nodes.new('ShaderNodeVertexColor')
attribute_node.layer_name = target.data.color_attributes.active_color.name
material.node_tree.links.new(attribute_node.outputs['Color'], nodes['Principled BSDF'].inputs['Base Color'])
nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.9
for obj in (target, dense):
    obj.data.materials.clear()
    obj.data.materials.append(material)

if not args.skip_silhouettes:
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 1
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = 320
    scene.render.use_persistent_data = True
    camera = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = diag * 1.05
    center = Vector(((points.min(0) + points.max(0)) / 2).tolist())
    ious = []
    for view in range(8):
        azimuth = math.radians(45 * view + 7.5)
        direction = Vector((math.sin(azimuth), -math.cos(azimuth), 0.35)).normalized()
        camera.location = center + direction * diag * 2
        camera.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
        masks = []
        for shown in (dense, target):
            dense.hide_render = shown is not dense
            target.hide_render = shown is not target
            path = os.path.join(args.out, f'silhouette-{view}-{shown.name}.png')
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            image = bpy.data.images.load(path)
            pixels = np.empty(len(image.pixels), dtype=np.float32)
            image.pixels.foreach_get(pixels)
            masks.append(pixels.reshape(-1, 4)[:, 3] > 0.5)
            bpy.data.images.remove(image)
        union = np.logical_or(*masks).sum()
        ious.append(float(np.logical_and(*masks).sum() / union) if union else 0.0)
    dense.hide_render = target.hide_render = False
    receipt['mesh']['silhouette_iou'] = {'views': [round(v, 5) for v in ious], 'mean': round(float(np.mean(ious)), 5),
                                         'min': round(min(ious), 5), 'gate_mean': 0.95}
phase('silhouettes')

# ---- 4. Fox template, canonicalized the same way ---------------------------------------------------------
bpy.ops.import_scene.gltf(filepath=args.fox)
fox_arm = next(o for o in scene.objects if o.type == 'ARMATURE')
fox_mesh = next(o for o in scene.objects if o.type == 'MESH' and o.parent == fox_arm)
for obj in list(scene.objects):
    if obj.type == 'MESH' and obj not in (target, dense, fox_mesh):
        bpy.data.objects.remove(obj)                     # bone-display Icosphere helper
fox_points, fox_tris = mesh_arrays(fox_mesh)
fox_matrix, fox_orientation = qf.canonicalize(fox_points.tolist())
fox_arm.matrix_world = Matrix(fox_matrix) @ fox_arm.matrix_world
bpy.context.view_layer.update()
fox_points, fox_tris = mesh_arrays(fox_mesh)
fox_heads = {b.name: tuple(fox_arm.matrix_world @ b.head_local) for b in fox_arm.data.bones}
if not fox_heads['b_Head_05'][1] < fox_heads['b_Hip_01'][1]:
    raise RuntimeError('Fox canonicalization did not put the authored head toward -Y')
receipt['template'] = {'source': 'Khronos glTF-Sample-Assets Fox (model CC0; rig/animation CC-BY 4.0)',
                       'joints': len(fox_heads), 'orientation': fox_orientation}

SPEC = {
    'spine': ['b_Root_00', 'b_Hip_01', 'b_Spine01_02', 'b_Spine02_03', 'b_Neck_04', 'b_Head_05'],
    'legs': {'fore_left': ['b_LeftUpperArm_09', 'b_LeftForeArm_010', 'b_LeftHand_011'],
             'fore_right': ['b_RightUpperArm_06', 'b_RightForeArm_07', 'b_RightHand_08'],
             'hind_left': ['b_LeftLeg01_015', 'b_LeftLeg02_016', 'b_LeftFoot01_017', 'b_LeftFoot02_018'],
             'hind_right': ['b_RightLeg01_019', 'b_RightLeg02_020', 'b_RightFoot01_021', 'b_RightFoot02_022']},
    'tail': ['b_Tail01_012', 'b_Tail02_013', 'b_Tail03_014'],
}

# ---- 5. Landmarks and template fit -------------------------------------------------------------------------
template_marks = qf.landmarks(fox_points.tolist(), fox_tris.tolist())
target_points, target_tris = points.tolist(), tris.tolist()
target_marks = qf.landmarks(target_points, target_tris)
fox_dense = qf.surface_samples(fox_points.tolist(), fox_tris.tolist(), 0.005 * template_marks['length'])
fitted = qf.fit_quadruped(fox_heads, template_marks, target_points, target_tris, target_marks, SPEC,
                          template_points=fox_dense)
joints = dict(fitted['joints'])
joints['_rootJoint'] = joints['b_Root_00']
nose = tuple(points[int(np.argmin(points[:, 1]))])
feet = target_marks['feet']
receipt['fit'] = {'scale_vs_template': fitted['scale'], 'height_ratio': fitted['height_ratio'], 'tail_found': fitted['tail_found'],
                  'warnings': fitted['warnings'], 'paw_counts': {k: v['count'] for k, v in feet.items()},
                  'paw_centers': {k: v['center'] for k, v in feet.items()}, 'joints': joints,
                  'method': 'landmark template fit: paws by floor contact, legs by slice centerlines, '
                            'spine/head by back-line depth, tail by geodesic rings'}
phase('fit')

TAIL_TO = {'b_Hip_01': 'b_Spine01_02', 'b_Spine01_02': 'b_Spine02_03', 'b_Spine02_03': 'b_Neck_04',
           'b_Neck_04': 'b_Head_05', 'b_Tail01_012': 'b_Tail02_013', 'b_Tail02_013': 'b_Tail03_014'}
for chain in SPEC['legs'].values():
    TAIL_TO.update(zip(chain, chain[1:]))
LEAF_TAILS = {'b_Head_05': nose,
              'b_LeftHand_011': feet['fore_left']['toe'], 'b_RightHand_08': feet['fore_right']['toe'],
              'b_LeftFoot02_018': feet['hind_left']['toe'], 'b_RightFoot02_022': feet['hind_right']['toe'],
              'b_Tail03_014': fitted['tail_tip'] or joints['b_Tail03_014']}

# ---- 6. Target armature: Fox hierarchy, names and roll references, fitted joints ----------------------------
rig = bpy.data.objects.new('CharacterRig', fox_arm.data.copy())
scene.collection.objects.link(rig)
rig.data.name = 'CharacterRig'
reference_z = {b.name: (fox_arm.matrix_world.to_3x3() @ b.matrix_local.to_3x3().col[2]).normalized()
               for b in fox_arm.data.bones}
activate(rig)
bpy.ops.object.mode_set(mode='EDIT')
minimum = 0.01 * diag
for bone in rig.data.edit_bones:
    bone.use_connect = False
for bone in rig.data.edit_bones:
    head = Vector(joints[bone.name])
    if bone.name in TAIL_TO:
        tail = Vector(joints[TAIL_TO[bone.name]])
    elif bone.name in LEAF_TAILS:
        tail = Vector(LEAF_TAILS[bone.name])
    else:                                                # non-deforming roots
        tail = head + Vector((0, 0.1 * diag, 0))
    if (tail - head).length < minimum:
        tail = head + Vector((0, 0, minimum))
    bone.head, bone.tail = head, tail
    bone.align_roll(reference_z[bone.name])
bpy.ops.object.mode_set(mode='OBJECT')
for name in ('_rootJoint', 'b_Root_00'):
    rig.data.bones[name].use_deform = False
if not fitted['tail_found']:
    for name in SPEC['tail']:
        rig.data.bones[name].use_deform = False
phase('armature')

# ---- 7. Heat-weight skinning (with watertight-proxy fallback) ----------------------------------------------
activate(target)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')


def unbound_count(obj):
    return sum(1 for v in obj.data.vertices if sum(g.weight for g in v.groups) <= 1e-8)


skin = {'method': 'blender-heat-direct', 'unbound_after_heat': unbound_count(target)}
if skin['unbound_after_heat']:
    # Heat diffusion needs a closed surface; skin a voxel-remeshed proxy, then transfer weights.
    proxy = target.copy()
    proxy.data = target.data.copy()
    scene.collection.objects.link(proxy)
    for group in list(proxy.vertex_groups):
        proxy.vertex_groups.remove(group)
    proxy.modifiers.clear()
    remesh = proxy.modifiers.new('remesh', 'REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = 0.006 * diag
    activate(proxy)
    bpy.ops.object.modifier_apply(modifier=remesh.name)
    proxy.parent = None
    activate(proxy)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    for group in list(target.vertex_groups):
        target.vertex_groups.remove(group)
    for group in proxy.vertex_groups:
        target.vertex_groups.new(name=group.name)
    transfer = target.modifiers.new('weights', 'DATA_TRANSFER')
    transfer.object = proxy
    transfer.use_vert_data = True
    transfer.data_types_verts = {'VGROUP_WEIGHTS'}
    transfer.vert_mapping = 'POLYINTERP_NEAREST'
    transfer.layers_vgroup_select_src = 'ALL'
    transfer.layers_vgroup_select_dst = 'NAME'
    activate(target)
    bpy.ops.object.modifier_move_to_index(modifier=transfer.name, index=0)
    bpy.ops.object.modifier_apply(modifier=transfer.name)
    bpy.data.objects.remove(proxy)
    skin.update(method='blender-heat-on-voxel-proxy+nearest-face-transfer', proxy_voxel=0.006 * diag)
activate(target)
bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
skin['unbound_final'] = unbound_count(target)
receipt['skin'] = skin
phase('skin')

# ---- 8. Retarget Fox Walk: world delta of each source bone applied to the fitted rest -----------------------
walk = bpy.data.actions['Walk_root']
fox_arm.animation_data.action = walk
first, last = (int(round(v)) for v in walk.frame_range)
order = sorted(rig.data.bones, key=lambda b: len(b.parent_recursive))
src_rest = {b.name: fox_arm.matrix_world @ b.matrix_local for b in fox_arm.data.bones}
dst_rest = {b.name: rig.matrix_world @ b.matrix_local for b in rig.data.bones}
for pose_bone in rig.pose.bones:
    pose_bone.rotation_mode = 'QUATERNION'
rig.animation_data_create()


BODY = {'b_Hip_01', 'b_Spine01_02', 'b_Spine02_03', 'b_Neck_04', 'b_Head_05'}


def retarget(hip_offset, name='Walk_inplace'):
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    action = bpy.data.actions.new(name)
    rig.animation_data.action = action
    previous = {}
    for frame in range(first, last + 1):
        scene.frame_set(frame)
        src_pose = {pb.name: fox_arm.matrix_world @ pb.matrix for pb in fox_arm.pose.bones}
        world = {}
        for bone in order:
            n = bone.name
            delta = src_pose[n].to_3x3().normalized() @ src_rest[n].to_3x3().normalized().inverted()
            if n in BODY and args.body_motion != 1.0:
                delta = Quaternion().slerp(delta.to_quaternion(), args.body_motion).to_matrix()
            rotation = (delta @ dst_rest[n].to_3x3().normalized()).to_quaternion()
            if bone.parent is None or n == 'b_Hip_01':
                moved = (src_pose[n].to_translation() - src_rest[n].to_translation()) * (
                    args.body_motion if n == 'b_Hip_01' else 1.0)
                head = dst_rest[n].to_translation() + moved * fitted['scale'] + (hip_offset if n == 'b_Hip_01' else Vector())
            else:
                parent = bone.parent.name
                head = world[parent] @ (dst_rest[parent].inverted() @ dst_rest[n].to_translation())
            world[n] = Matrix.LocRotScale(head, rotation, None)
        for bone in order:
            n = bone.name
            parent_world = world[bone.parent.name] if bone.parent else Matrix.Identity(4)
            parent_rest = dst_rest[bone.parent.name] if bone.parent else Matrix.Identity(4)
            basis = (parent_rest.inverted() @ dst_rest[n]).inverted() @ (parent_world.inverted() @ world[n])
            pose_bone = rig.pose.bones[n]
            q = basis.to_quaternion()
            if n in previous and previous[n].dot(q) < 0:
                q.negate()
            previous[n] = q
            pose_bone.rotation_quaternion = q
            pose_bone.keyframe_insert('rotation_quaternion', frame=frame)
            if bone.parent is None or n == 'b_Hip_01':
                pose_bone.location = basis.to_translation()
                pose_bone.keyframe_insert('location', frame=frame)
    return action


fps = scene.render.fps
duration = (last - first) / fps
cycle = list(range(first, last))                         # the last key repeats the first pose
LEAVES = {'fore_left': ('b_LeftHand_011', 3), 'fore_right': ('b_RightHand_08', 3),
          'hind_left': ('b_LeftFoot02_018', 4), 'hind_right': ('b_RightFoot02_022', 4)}
paw_vertices = {}
for leg, data in feet.items():
    cx, cy, _ = data['center']
    paw_vertices[leg] = np.where((points[:, 2] <= 0.06 * target_marks['height'])
                                 & (np.hypot(points[:, 0] - cx, points[:, 1] - cy) <= 0.03 * diag))[0]
edges = np.array([(e.vertices[0], e.vertices[1]) for e in target.data.edges])
rest_len = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)


def skinned(depsgraph):
    evaluated = target.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get('co', co)
    evaluated.to_mesh_clear()
    world = np.array(target.matrix_world)
    return co.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]


def measure(stride, samples=60, reach_targets=None):
    """Contact, seam and deformation metrics of the current action, normalized by L (bbox diagonal)."""
    count = max(4, int(round(duration * samples)))
    lows, fronts, stretch = {leg: [] for leg in feet}, {leg: [] for leg in feet}, []
    joints_at, toes, reach = [], {leg: [] for leg in feet}, []
    for i in range(count + 1):
        t = first + (last - first) * i / count
        scene.frame_set(int(math.floor(t)), subframe=t - math.floor(t))
        co = skinned(bpy.context.evaluated_depsgraph_get())
        for leg, idx in paw_vertices.items():
            paw = co[idx]
            lows[leg].append(float(paw[:, 2].min()))
            fronts[leg].append(float(-paw[paw[:, 2].argsort()[:8]][:, 1].mean()))
        for leg, (bone, _) in LEAVES.items():
            toes[leg].append(rig.matrix_world @ rig.pose.bones[bone].tail)
            if reach_targets:
                joint = rig.matrix_world @ rig.pose.bones[bone].head
                reach.append((joint - reach_targets[leg].matrix_world.translation).length)
        if i in (0, count):
            joints_at.append({b.name: rig.matrix_world @ b.head for b in rig.pose.bones})
        ratio = np.linalg.norm(co[edges[:, 0]] - co[edges[:, 1]], axis=1) / np.maximum(rest_len, 1e-12)
        stretch.append(((ratio > 2).mean(), (ratio < 0.5).mean(), np.percentile(ratio, 99)))
    dt, speed, contact = duration / count, stride / duration, {}
    for leg in feet:
        low, front = np.array(lows[leg]), np.array(fronts[leg])
        planted = low <= low.min() + 0.15 * (low.max() - low.min())
        worst, run = 0.0, []
        for i, flag in enumerate(list(planted) + [False]):
            if flag:
                run.append(i)
            elif len(run) > 1:
                worst = max(worst, max(abs(front[j] - front[run[0]] + speed * (j - run[0]) * dt) for j in run))
                run = []
            else:
                run = []
        try:
            implied = qf.stride_from_contact(front[:-1].tolist(), low[:-1].tolist(), duration)
        except ValueError as error:
            implied = str(error)
        toe = toes[leg]
        toe_low = np.array([p.z for p in toe])
        toe_planted = toe_low <= toe_low.min() + 0.15 * (toe_low.max() - toe_low.min())
        toe_worst, run = 0.0, []
        for i, flag in enumerate(list(toe_planted) + [False]):
            if flag:
                run.append(i)
            elif len(run) > 1:
                toe_worst = max(toe_worst, max(abs(-toe[j].y + toe[run[0]].y + speed * (j - run[0]) * dt) for j in run))
                run = []
            else:
                run = []
        # Stance from the clip annotation (planted path frames), independent of the measured paw heights.
        span = last - first
        annotated = [(first + math.floor(i * span / count) % span) in stance_frames[leg]
                     and (first + math.ceil(i * span / count) % span) in stance_frames[leg]
                     for i in range(count + 1)]                # cyclic: the final key is the first pose
        annotated_worst, run = 0.0, []
        for i, flag in enumerate(annotated + [False]):
            if flag:
                run.append(i)
            elif len(run) > 1:
                annotated_worst = max(annotated_worst, max(abs(front[j] - front[run[0]] + speed * (j - run[0]) * dt)
                                                           for j in run))
                run = []
            else:
                run = []
        contact[leg] = {'annotated_stance_sliding_over_L': annotated_worst / diag,
                        'annotated_stance_max_height_over_L': float(max((low[i] for i, f in enumerate(annotated) if f),
                                                                        default=float('nan')) / diag),
                        'stance_sliding_over_L': worst / diag, 'toe_point_sliding_over_L': toe_worst / diag,
                        'penetration_over_L': max(0.0, -low.min()) / diag,
                        'hover_in_stance_over_L': float(low[planted].max() / diag),
                        'lift_over_L': float((low.max() - low.min()) / diag), 'implied_stride': implied,
                        'stance_fraction': float(planted.mean())}
    seam = max((joints_at[0][n] - joints_at[1][n]).length for n in joints_at[0]) / diag
    stretch = np.array(stretch)
    return {'contact': contact, 'loop_position_seam_over_L': seam,
            'worst_annotated_sliding_over_L': max(c['annotated_stance_sliding_over_L'] for c in contact.values()),
            'worst_sliding_over_L': max(c['stance_sliding_over_L'] for c in contact.values()),
            'worst_penetration_over_L': max(c['penetration_over_L'] for c in contact.values()),
            'worst_toe_point_sliding_over_L': max(c['toe_point_sliding_over_L'] for c in contact.values()),
            'ik_reach_error_max_over_L': (max(reach) / diag) if reach else None,
            'edge_stretch': {'max_over_2x_fraction': float(stretch[:, 0].max()),
                             'max_under_half_fraction': float(stretch[:, 1].max()),
                             'max_p99_ratio': float(stretch[:, 2].max())},
            'sampling': f'{count} intervals over one cycle (~{samples} Hz), skinned paw vertices'}


# Stride and contact timing come from the authored Fox's own skinned paw vertices, scaled to the target.
fox_paw_vertices = {}
for leg, data in template_marks['feet'].items():
    cx, cy, _ = data['center']
    fox_diag = float(np.linalg.norm(fox_points.max(0) - fox_points.min(0)))
    fox_paw_vertices[leg] = np.where((fox_points[:, 2] <= 0.06 * template_marks['height'])
                                     & (np.hypot(fox_points[:, 0] - cx, fox_points[:, 1] - cy) <= 0.03 * fox_diag))[0]
source_tracks = {leg: [] for leg in LEAVES}
for frame in cycle:
    scene.frame_set(frame)
    evaluated = fox_mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get('co', co)
    evaluated.to_mesh_clear()
    world = np.array(fox_mesh.matrix_world)
    co = co.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]
    for leg in LEAVES:
        paw = co[fox_paw_vertices[leg]]
        lowest = paw[paw[:, 2].argsort()[:4]]
        source_tracks[leg].append(Vector((lowest[:, 0].mean(), lowest[:, 1].mean(), paw[:, 2].min())))
fox_strides = [qf.stride_from_contact([-p.y for p in track], [p.z for p in track], duration)
               for track in source_tracks.values()]
stride = float(np.median(fox_strides)) * fitted['scale']
receipt['motion'] = {'source_clip': 'Fox Walk (authored, CC-BY 4.0)', 'gait': args.gait,
                     'body_motion_kept': args.body_motion, 'frames': [first, last], 'fps': fps,
                     'fox_paw_vertex_counts': {k: len(v) for k, v in fox_paw_vertices.items()},
                     'duration_s': duration, 'fox_strides': fox_strides, 'stride_model_units': stride,
                     'gates': {'stance_sliding_over_L': 0.02, 'penetration_over_L': 0.005, 'loop_seam_over_L': 0.005}}

# Lateral-sequence walk: left hind, left fore, right hind, right fore, each planted 65% of the cycle.
PHASES = {'hind_left': 0.0, 'fore_left': 0.25, 'hind_right': 0.5, 'fore_right': 0.75}
DUTY = 0.65
if args.gait == 'procedural':
    # Keep the planted sweep (duty x stride) within reach: 0.5 x the mean shoulder/hip joint height.
    leg_height = float(np.mean([joints[chain[0]][2] for chain in SPEC['legs'].values()]))
    stride = 0.5 * leg_height / DUTY
    receipt['motion'].update(stride_model_units=stride, stride_rule='0.5 x mean leg-top height / duty 0.65')
paths = {}
for leg in LEAVES:
    lows = [p.z for p in source_tracks[leg]]
    lift = (max(lows) - min(lows)) * fitted['scale']
    if args.gait == 'procedural':
        n = len(cycle)
        lows = [0.0 if ((i / n - PHASES[leg]) % 1) < DUTY else
                math.sin(math.pi * (((i / n - PHASES[leg]) % 1) - DUTY) / (1 - DUTY)) for i in range(n)]
    paths[leg] = qf.planted_paw_path(lows, stride, lift)
stance_frames = {leg: {cycle[i] for i, (_, h) in enumerate(path) if h == 0} for leg, path in paths.items()}
receipt['motion']['annotated_stance_fraction'] = {leg: len(f) / len(cycle) for leg, f in stance_frames.items()}

retarget(Vector())
linear_keys(rig)
receipt['motion']['fk_retarget_only'] = measure(stride)
phase('retarget')

# IK paw planting: the wrist/ankle follows a planted path (fixed on the ground, moving back at body speed
# through each stance) and each paw bone keeps its rest world orientation, so paws stay flat.
targets, helpers = {}, []
for leg, (bone, chain) in LEAVES.items():
    path = paths[leg]
    leaf = rig.data.bones[bone]
    rest_joint = rig.matrix_world @ leaf.head_local
    empty = bpy.data.objects.new(f'ik-{leg}', None)
    scene.collection.objects.link(empty)
    for frame, (forward, height) in zip(cycle + [last], path + [path[0]]):
        empty.location = rest_joint + Vector((0, -forward, height))
        empty.keyframe_insert('location', frame=frame)
    linear_keys(empty)
    constraint = rig.pose.bones[leaf.parent.name].constraints.new('IK')
    constraint.target = empty
    constraint.chain_count = chain - 1
    constraint.use_tail = True
    constraint.use_stretch = False
    orient = bpy.data.objects.new(f'flat-{leg}', None)
    scene.collection.objects.link(orient)
    orient.matrix_world = rig.matrix_world @ leaf.matrix_local
    flat = rig.pose.bones[bone].constraints.new('COPY_ROTATION')
    flat.target = orient
    flat.owner_space = flat.target_space = 'WORLD'
    targets[leg] = empty
    helpers += [empty, orient]
receipt['motion']['ik_constraints_live'] = measure(stride, reach_targets=targets)
activate(rig)
bpy.ops.object.mode_set(mode='POSE')
for pose_bone in rig.pose.bones:
    pose_bone.bone.select = True
bpy.ops.nla.bake(frame_start=first, frame_end=last, only_selected=False, visual_keying=True,
                 clear_constraints=True, use_current_action=True, bake_types={'POSE'})
bpy.ops.object.mode_set(mode='OBJECT')
for helper in helpers:
    bpy.data.objects.remove(helper)
rig.animation_data.action.name = 'Walk_inplace'
linear_keys(rig)                                         # glTF/Three.js interpolate keys linearly
receipt['motion']['ik_planted'] = measure(stride)
timing = 'Fox contact timing' if args.gait == 'fox' else '4-beat lateral-sequence timing, 65% stance'
receipt['motion']['method'] = ('FK: per-bone world rotation deltas of Fox Walk applied to the fitted rest; '
                               f'IK: wrists/ankles pinned along planted paths from {timing}; paw bones held at '
                               'rest world orientation; baked to linear keys')
phase('measure')

# ---- 10. Export: runtime forward is +X in glTF, so turn canonical -Y forward by +90 degrees about Z ----------
for obj in (fox_arm, fox_mesh, dense):
    bpy.data.objects.remove(obj)
for action in list(bpy.data.actions):
    if action != rig.animation_data.action:
        bpy.data.actions.remove(action)
rig.rotation_euler = (0, 0, math.pi / 2)
scene.frame_set(first)
bpy.ops.object.select_all(action='DESELECT')
rig.select_set(True)
target.select_set(True)
glb = os.path.join(args.out, 'character.glb')
bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_animations=True,
                          export_animation_mode='ACTIONS', export_skins=True, export_all_influences=False,
                          export_def_bones=False, export_yup=True, export_force_sampling=True,
                          export_vertex_color='ACTIVE')
receipt['export'] = {'glb': os.path.basename(glb), 'bytes': os.path.getsize(glb), 'sha256': sha256(glb),
                     'skin_report': qf.glb_skin_report(glb), 'runtime_forward': '+X (glTF)', 'clip': 'Walk_inplace'}
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, 'character.blend'))
phase('export')
receipt['total_seconds'] = round(time.perf_counter() - started, 3)
save()
print('SLICE_A_DONE', json.dumps({'stride': stride, 'triangles': receipt['mesh']['prepared_triangles']}))
