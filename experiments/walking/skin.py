"""Experimental continuous skin transfer; run in the locked UniRig environment.

All Blender/model imports are deferred. Inputs are preserved; candidates require
standing and motion review before any app integration.
"""
import argparse
import hashlib
import json
from pathlib import Path


def fit_similarity(source,target):
    import numpy as np
    source=np.asarray(source,float);target=np.asarray(target,float)
    if source.shape!=target.shape or source.ndim!=2 or source.shape[1]!=3 or len(source)<4:
        raise ValueError('Joint arrays must match and contain at least four correspondences')
    if not np.isfinite(source).all() or not np.isfinite(target).all():raise ValueError('Nonfinite joints')
    x=source-source.mean(0);y=target-target.mean(0)
    if np.linalg.matrix_rank(x)<3 or np.linalg.matrix_rank(y)<3:raise ValueError('Joint alignment is underdetermined')
    u,s,v=np.linalg.svd(x.T@y);rotation=u@v
    if np.linalg.det(rotation)<0:raise ValueError('Joint alignment would mirror anatomy')
    scale=s.sum()/(x*x).sum();shift=target.mean(0)-scale*source.mean(0)@rotation
    error=float(np.linalg.norm(scale*source@rotation+shift-target,axis=1).max())
    extent=float(np.linalg.norm(np.ptp(target,axis=0)))
    if scale<=0 or error>max(1e-6,extent*1e-4):raise ValueError('Joint correspondence is inconsistent with a rigid scaled skeleton')
    return scale,rotation,shift,error


def transfer_weights(vertices,faces,weights,points,*,steps=0):
    import numpy as np
    import open3d as o3d
    from scipy.sparse import coo_matrix
    vertices=np.asarray(vertices,float);faces=np.asarray(faces);weights=np.asarray(weights,float);points=np.asarray(points,float)
    if not isinstance(steps,int) or not 0<=steps<=128:raise ValueError('Smoothing steps must be between 0 and 128')
    if vertices.ndim!=2 or vertices.shape[1]!=3 or points.ndim!=2 or points.shape[1]!=3 or not len(points):raise ValueError('Invalid points')
    if faces.ndim!=2 or faces.shape[1]!=3 or not len(faces) or not np.issubdtype(faces.dtype,np.integer):raise ValueError('Invalid triangles')
    if faces.min()<0 or faces.max()>=len(vertices):raise ValueError('Triangle indices exceed vertex count')
    if weights.ndim!=2 or len(weights)!=len(vertices) or not weights.shape[1]:raise ValueError('Invalid skin dimensions')
    if any(not np.isfinite(a).all() for a in (vertices,weights,points)) or weights.min()<0 or np.any(weights.sum(1)<=0):raise ValueError('Invalid/unweighted source or nonfinite geometry')
    weights=weights/weights.sum(1)[:,None]
    if steps:
        edges=np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]))
        edges=np.unique(np.sort(edges,axis=1),axis=0);n=len(weights)
        rows=np.concatenate((edges[:,0],edges[:,1],np.arange(n)));cols=np.concatenate((edges[:,1],edges[:,0],np.arange(n)))
        matrix=coo_matrix((np.ones(len(rows)),(rows,cols)),shape=(n,n)).tocsr()
        matrix=matrix.multiply(1/np.asarray(matrix.sum(axis=1))).tocsr()
        for _ in range(steps):weights=.5*weights+.5*(matrix@weights)
    area=np.linalg.norm(np.cross(vertices[faces[:,1]]-vertices[faces[:,0]],vertices[faces[:,2]]-vertices[faces[:,0]]),axis=1)
    faces=faces[area>1e-12]
    if not len(faces):raise ValueError('Source contains no nondegenerate triangles')
    mesh=o3d.t.geometry.TriangleMesh(o3d.core.Tensor(vertices.astype(np.float32)),o3d.core.Tensor(faces.astype(np.uint32)))
    scene=o3d.t.geometry.RaycastingScene();scene.add_triangles(mesh)
    closest=scene.compute_closest_points(o3d.core.Tensor(points.astype(np.float32)))
    indices=closest['primitive_ids'].numpy();uv=closest['primitive_uvs'].numpy()
    if np.any(indices>=len(faces)):raise ValueError('No source surface was found')
    bary=np.maximum(np.column_stack((1-uv.sum(1),uv)),0);bary/=bary.sum(1)[:,None]
    result=(weights[faces[indices]]*bary[:,:,None]).sum(1)
    ids=np.argsort(-result,axis=1)[:,:4];limited=np.zeros_like(result)
    np.put_along_axis(limited,ids,np.take_along_axis(result,ids,axis=1),axis=1)
    if not np.isfinite(limited).all() or np.any(limited.sum(1)<=0):raise ValueError('Surface transfer produced invalid weights')
    limited/=limited.sum(1)[:,None]
    distances=np.linalg.norm(closest['points'].numpy()-points,axis=1)
    return limited,{'distance_p95':float(np.quantile(distances,.95)),'distance_max':float(distances.max()),'smoothing_steps':steps}


def collect(path):
    import bpy
    import numpy as np
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if path.suffix.lower()=='.fbx':bpy.ops.import_scene.fbx(filepath=str(path.resolve()))
    elif path.suffix.lower()=='.glb':bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    else:raise ValueError('Use a skin FBX or GLB')
    armatures=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
    if len(armatures)!=1:raise ValueError('Expected one skin armature')
    armature=armatures[0];armature.animation_data_clear()
    names=[b.name for b in armature.data.bones];indices={name:i for i,name in enumerate(names)}
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==armature for m in o.modifiers)]
    if not meshes:raise ValueError('No bound mesh')
    vertices=[];faces=[];weights=[]
    for obj in meshes:
        offset=len(vertices);obj.data.calc_loop_triangles()
        vertices.extend(tuple(obj.matrix_world@v.co) for v in obj.data.vertices)
        faces.extend(tuple(offset+i for i in t.vertices) for t in obj.data.loop_triangles)
        for vertex in obj.data.vertices:
            row=np.zeros(len(names))
            for group in vertex.groups:
                name=obj.vertex_groups[group.group].name
                if name in indices:row[indices[name]]=group.weight
            weights.append(row)
    joints=np.array([tuple(armature.matrix_world@b.head_local) for b in armature.data.bones])
    return {'vertices':np.asarray(vertices),'faces':np.asarray(faces),'weights':np.asarray(weights),'joints':joints,'names':names},meshes,armature


def run(args):
    import bpy
    import numpy as np
    if args.output.exists():raise ValueError('Output directory already exists; preserve existing results')
    inputs={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.source,args.target)}
    source,_,_=collect(args.source);target,meshes,armature=collect(args.target)
    if set(source['names'])!=set(target['names']):raise ValueError('Source and target bone names must match exactly')
    order=[source['names'].index(n) for n in target['names']]
    scale,rotation,shift,error=fit_similarity(source['joints'][order],target['joints'])
    vertices=source['vertices']@rotation*scale+shift
    weights,report=transfer_weights(vertices,source['faces'],source['weights'][:,order],target['vertices'],steps=args.smoothing_steps)
    offset=0
    for obj in meshes:
        count=len(obj.data.vertices);rows=weights[offset:offset+count];offset+=count
        for group in obj.vertex_groups:group.remove(list(range(count)))
        ids=np.argsort(-rows,axis=1)[:,:4]
        for i in range(count):
            for j in ids[i]:
                if rows[i,j]>0:obj.vertex_groups[target['names'][j]].add([i],float(rows[i,j]),'REPLACE')
    # No reposing or geometry correction: this candidate changes only skin weights.
    args.output.mkdir(parents=True)
    bpy.ops.export_scene.gltf(filepath=str((args.output/'corrected.glb').resolve()),export_format='GLB',export_animations=False)
    if any(hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest for path,digest in inputs.items()):raise ValueError('An input changed during correction')
    report.update(joint_alignment_error_max=error,scale=scale,inputs=inputs,vertices=len(target['vertices']),
                  triangles=len(target['faces']),bones=len(target['names']),scope='Unreviewed skin candidate; no walking acceptance.')
    (args.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','target','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--smoothing-steps',type=int,default=0)
    run(parser.parse_args())


if __name__=='__main__':
    import os
    import sys
    import traceback
    try:main()
    except Exception:
        traceback.print_exc();code=1
    else:code=0
    sys.stdout.flush();sys.stderr.flush();os._exit(code)
