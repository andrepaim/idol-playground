"""Disposable standing-pose probe, not a natural-walk generator.

Run in the existing Blender environment. Mapping and owner assets remain external.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def validate_mapping(rows, target_names, source_names):
    if not isinstance(rows,list) or not rows:raise ValueError('Provide an explicit nonempty joint mapping')
    seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Invalid mapping row')
        target,source=row.get('target'),row.get('source')
        if not isinstance(target,str) or not isinstance(source,str):raise ValueError('Invalid joint names')
        if target not in target_names or source not in source_names or target in seen:
            raise ValueError('Unknown or repeated mapped joint')
        degrees=row.get('degrees',0)
        if not isinstance(degrees,(int,float)) or not math.isfinite(degrees) or abs(degrees)>180:
            raise ValueError('Invalid explicit pose angle')
        seen.add(target)
    return rows


def sagittal_rotation(rest,desired):
    for vector in (rest,desired):
        if len(vector)!=3 or not all(math.isfinite(x) for x in vector) or math.hypot(vector[0],vector[2])<1e-8:
            raise ValueError('Unusable sagittal direction')
    return math.atan2(rest[2],rest[0])-math.atan2(desired[2],desired[0])


def summarize_stretch(ratios):
    values=sorted(float(x) for x in ratios)
    if not values or any(not math.isfinite(x) or x<0 for x in values):raise ValueError('Invalid edge stretch')
    def percentile(p):
        index=(len(values)-1)*p;lo=int(index);hi=min(lo+1,len(values)-1)
        return values[lo]+(values[hi]-values[lo])*(index-lo)
    return {'edge_count':len(values),'p95':percentile(.95),'p99':percentile(.99),
            'over_2_fraction':sum(x>2 for x in values)/len(values)}


def run(args):
    import bpy
    import numpy as np
    from mathutils import Vector,Quaternion,Matrix
    if args.output.exists():raise ValueError('Output must be a new directory; existing artifacts are preserved')
    digest=hashlib.sha256(args.input.read_bytes()).hexdigest()
    mapping=json.loads(args.mapping.read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module='io_anim_bvh')
    bpy.ops.import_anim.bvh(filepath=str(args.motion.resolve()),axis_forward='-Z',axis_up='Y',
                            use_fps_scale=False,update_scene_fps=True,update_scene_duration=True)
    reference=bpy.context.object
    if not 1<=args.frame<=bpy.context.scene.frame_end:raise ValueError('Reference frame outside imported animation')
    bpy.context.scene.frame_set(args.frame)
    forward=reference.pose.bones[mapping['source_chest']].head-reference.pose.bones[mapping['source_hips']].head
    if math.hypot(forward.x,forward.y)<1e-8:raise ValueError('Cannot establish reference heading')
    yaw=Quaternion(Vector((0,0,1)),-math.atan2(forward.y,forward.x))
    directions={b.name:yaw@(b.tail-b.head) for b in reference.pose.bones}
    directions[mapping['source_hips']]=yaw@forward
    bpy.data.objects.remove(reference,do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=str(args.input.resolve()))
    armatures=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
    if len(armatures)!=1:raise ValueError('Expected one target armature')
    armature=armatures[0];armature.animation_data_clear()
    rows=validate_mapping(mapping['joints'],set(armature.data.bones.keys()),set(directions))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    def vertices():
        bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get();result=[]
        for obj in meshes:
            evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh()
            result.extend(tuple(v.co) for v in mesh.vertices);evaluated.to_mesh_clear()
        return np.asarray(result)
    before=vertices();edges=[];offset=0
    for obj in meshes:
        edges.extend((e.vertices[0]+offset,e.vertices[1]+offset) for e in obj.data.edges);offset+=len(obj.data.vertices)
    by_name={row['target']:row for row in rows}
    # Blender's bone order is parent before child; reject a contrary hierarchy.
    visited=set()
    for bone in armature.pose.bones:
        if bone.parent and bone.parent.name not in visited:raise ValueError('Unexpected bone traversal order')
        visited.add(bone.name)
        if bone.name not in by_name:continue
        row=by_name[bone.name];rest=bone.bone.tail_local-bone.bone.head_local
        if bone.name==mapping['target_hips']:
            rest=armature.data.bones[mapping['target_chest']].head_local-bone.bone.head_local
        desired=directions[row['source']]
        if row.get('hold'):angle=0
        elif 'degrees' in row:
            radians=math.radians(row['degrees']);angle=sagittal_rotation(rest,(math.cos(radians),0,math.sin(radians)))
        else:angle=sagittal_rotation(rest,desired)
        q=Quaternion(Vector((0,1,0)),angle)@bone.bone.matrix_local.to_quaternion()
        bone.matrix=Matrix.LocRotScale(bone.head.copy(),q,Vector((1,1,1)));bpy.context.view_layer.update()
    after=vertices();edges=np.asarray(edges)
    original=np.linalg.norm(before[edges[:,0]]-before[edges[:,1]],axis=1)
    posed=np.linalg.norm(after[edges[:,0]]-after[edges[:,1]],axis=1);valid=original>1e-6
    report={'deformation':summarize_stretch(posed[valid]/original[valid]),'mapped_joints':len(rows),
            'source_sha256':digest,'motion_sha256':hashlib.sha256(args.motion.read_bytes()).hexdigest(),
            'mapping':mapping,'reference_frame':args.frame,'scope':'Pose feasibility only; requires visual review and contact validation.'}
    args.output.mkdir(parents=True)
    bpy.context.scene.frame_start=1;bpy.context.scene.frame_end=2
    for bone in armature.pose.bones:
        bone.rotation_mode='QUATERNION'
        for frame in (1,2):
            for channel in ('location','rotation_quaternion','scale'):bone.keyframe_insert(data_path=channel,frame=frame)
    armature.animation_data.action.name='Standing feasibility'
    bpy.context.scene.frame_set(1)
    bpy.ops.export_scene.gltf(filepath=str((args.output/'pose.glb').resolve()),export_format='GLB',
                              export_animations=True,export_frame_range=True,export_force_sampling=True)
    if hashlib.sha256(args.input.read_bytes()).hexdigest()!=digest:raise ValueError('Source changed during probe')
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report['deformation']),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('input','motion','mapping','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--frame',type=int,default=100)
    run(parser.parse_args())


if __name__=='__main__':
    # bpy in this accepted WSL environment can crash at interpreter teardown.
    # Exit only after run's explicit checks and flushed output; failures stay nonzero.
    import os
    import sys
    import traceback
    try:main()
    except Exception:
        traceback.print_exc();code=1
    else:code=0
    sys.stdout.flush();sys.stderr.flush();os._exit(code)
