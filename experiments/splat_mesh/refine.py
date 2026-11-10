"""CPU-only fusion of recorded stereo depth, with explicit small-fragment cleanup and upright export."""
import argparse
import json
from pathlib import Path
import struct
import time
import numpy as np
import open3d as o3d
import trimesh
from PIL import Image


def appearance_glb(mesh):
    """glTF vertex colors are linear; keep captured appearance unlit for faithful comparison."""
    colors=mesh.visual.vertex_colors.astype(np.float32)/255
    rgb=colors[:,:3]
    colors[:,:3]=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    data=mesh.export(file_type='glb',include_normals=True)
    length=struct.unpack_from('<I',data,12)[0]
    doc=json.loads(data[20:20+length]);binary=data[28+length:]
    begin=len(binary);packed=colors.astype('<f4').tobytes();binary+=packed
    view=len(doc['bufferViews'])
    doc['bufferViews'].append({'buffer':0,'byteOffset':begin,'byteLength':len(packed),'target':34962})
    for item in doc['meshes']:
        for primitive in item['primitives']:
            accessor=doc['accessors'][primitive['attributes']['COLOR_0']]
            accessor.update(bufferView=view,componentType=5126,type='VEC4',count=len(colors))
            for field in ['normalized','byteOffset','min','max']:accessor.pop(field,None)
    doc['buffers'][0]['byteLength']=len(binary)
    doc.setdefault('extensionsUsed',[]).append('KHR_materials_unlit')
    doc['materials']=[{'doubleSided':True,'extensions':{'KHR_materials_unlit':{}},'pbrMetallicRoughness':{'metallicFactor':0,'roughnessFactor':1}}]
    for item in doc['meshes']:
        for primitive in item['primitives']:primitive['material']=0
    encoded=json.dumps(doc).encode();encoded+=b' '*(-len(encoded)%4)
    chunks=struct.pack('<I4s',len(encoded),b'JSON')+encoded+struct.pack('<I4s',len(binary),b'BIN\0')+binary
    return struct.pack('<4sII',b'glTF',2,len(chunks)+12)+chunks


def refine(args):
    args.output.mkdir(parents=True,exist_ok=True);start=time.monotonic()
    manifest=json.loads((args.views/'views.json').read_text())
    volume=o3d.pipelines.integration.ScalableTSDFVolume(voxel_length=args.voxel,sdf_trunc=args.voxel*5,
                                                      color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    for index,pair in enumerate(manifest['pairs']):
        camera=pair['left'];rgba=np.asarray(Image.open(args.views/camera['file']).convert('RGBA'))
        alpha=rgba[...,3:4].astype(np.float32)/255
        rgb=np.uint8(np.clip(rgba[...,:3]*alpha+127*(1-alpha),0,255))
        depth=np.load(args.depths/f'{index:03}-depth.npy')
        rgbd=o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(np.ascontiguousarray(rgb)),o3d.geometry.Image(depth),
                     depth_scale=1.,depth_trunc=2.25,convert_rgb_to_intensity=False)
        K=o3d.camera.PinholeCameraIntrinsic(camera['size'],camera['size'],camera['focal'],camera['focal'],camera['size']/2,camera['size']/2)
        volume.integrate(rgbd,K,np.asarray(camera['extrinsic']))
    raw=volume.extract_triangle_mesh();raw.compute_vertex_normals()
    o3d.io.write_triangle_mesh(str(args.output/'raw.ply'),raw)
    mesh=trimesh.Trimesh(np.asarray(raw.vertices),np.asarray(raw.triangles),vertex_colors=np.uint8(np.asarray(raw.vertex_colors)*255),process=False)
    parts=trimesh.graph.connected_components(mesh.face_adjacency,nodes=np.arange(len(mesh.faces)),min_len=1)
    retained=max(parts,key=len) if args.largest_component else np.concatenate([indices for indices in parts if len(indices)>=args.minimum_component])
    removed=len(mesh.faces)-len(retained)
    mesh.update_faces(retained);mesh.remove_unreferenced_vertices();mesh.fix_normals()
    if not np.isfinite(mesh.vertices).all() or not len(mesh.faces):raise ValueError('Invalid refined geometry')
    mesh.export(args.output/'mesh.ply')
    (args.output/'mesh-reference.glb').write_bytes(appearance_glb(mesh))
    upright=mesh.copy();upright.apply_transform(np.diag([1,-1,-1,1]));(args.output/'mesh.glb').write_bytes(appearance_glb(upright))
    report={'voxel':args.voxel,'vertices':len(mesh.vertices),'triangles':len(mesh.faces),'removed_small_fragment_triangles':removed,
            'minimum_component_faces':args.minimum_component,'largest_component_only':args.largest_component,'watertight':bool(mesh.is_watertight),
            'seconds':round(time.monotonic()-start,2),'appearance':'unlit linear vertex colors; no UV texture map',
            'mesh.glb':'upright glTF Y-up; X rotation pi from the source splat coordinate frame',
            'mesh-reference.glb':'source PLY coordinates for calibrated comparison'}
    (args.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--views',type=Path,required=True)
    parser.add_argument('--depths',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--voxel',type=float,default=.002)
    parser.add_argument('--minimum-component',type=int,default=100)
    parser.add_argument('--largest-component',action='store_true',help='Keep one connected subject; retain raw.ply for accessories/fragments')
    refine(parser.parse_args())


if __name__=='__main__':main()
