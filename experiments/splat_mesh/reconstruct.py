"""Calibrated splat-view stereo and TSDF fusion; experiment only, no app integration."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from PIL import Image


def load_view(path):
    rgba=np.asarray(Image.open(path).convert('RGBA'))
    alpha=rgba[...,3].astype(np.float32)/255
    rgb=np.uint8(np.clip(rgba[...,:3]*alpha[...,None]+127*(1-alpha[...,None]),0,255))
    return rgb,alpha


def valid_depth(left,right,alpha,focal,baseline,*,tolerance=1.5):
    h,w=left.shape
    yy,xx=np.mgrid[:h,:w]
    finite=np.isfinite(left)&(left>0)
    target=np.rint(xx-np.where(finite,left,0)).astype(int)
    sampled=right[yy,np.clip(target,0,w-1)]
    valid=finite&np.isfinite(sampled)&(sampled>0)&(target>=0)&(target<w)&(np.abs(left-sampled)<=tolerance)&(alpha>.75)
    depth=np.divide(focal*baseline,left,out=np.zeros_like(left),where=finite)
    valid&=(depth>.75)&(depth<2.25)
    depth[~valid]=0
    return depth,valid


def neural_model(source,checkpoint):
    from argparse import Namespace
    import torch
    sys.path.insert(0,str(source/'third_party/DLNR'))
    from core.dlnr import DLNR
    args=Namespace(corr_implementation='reg',corr_levels=4,corr_radius=4,dataset='things',
                   hidden_dims=[128,128,128],mixed_precision=True,n_downsample=2,n_gru_layers=3,
                   shared_backbone=False,slow_fast_gru=False)
    model=DLNR(args)
    state=torch.load(checkpoint,map_location='cpu',weights_only=True)
    model.load_state_dict({key.removeprefix('module.'):value for key,value in state.items()})
    model.cuda().eval()
    return model


def neural_pair(model,left,right,iters):
    import torch
    from core.utils.utils import InputPadder
    a=torch.from_numpy(left.copy()).permute(2,0,1)[None].float().cuda()
    b=torch.from_numpy(right.copy()).permute(2,0,1)[None].float().cuda()
    pad=InputPadder(a.shape,divis_by=32)
    a,b=pad.pad(a,b)
    output=[]
    with torch.inference_mode():
        for one,two,flip in [(a,b,False),(torch.flip(b,[3]),torch.flip(a,[3]),True)]:
            _,flow=model(one,two,iters=iters,test_mode=True)
            if flip:flow=torch.flip(flow,[3])
            disparity=-pad.unpad(flow).squeeze().float().cpu().numpy()
            output.append(disparity)
    return output


def classical_pair(left,right):
    a=cv2.cvtColor(left,cv2.COLOR_RGB2GRAY);b=cv2.cvtColor(right,cv2.COLOR_RGB2GRAY)
    matcher=cv2.StereoSGBM_create(minDisparity=0,numDisparities=128,blockSize=5,P1=8*25,P2=32*25,
                                 disp12MaxDiff=1,uniquenessRatio=8,speckleWindowSize=60,speckleRange=2,
                                 mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY)
    return [matcher.compute(a,b).astype(np.float32)/16,
            np.fliplr(matcher.compute(np.fliplr(b).copy(),np.fliplr(a).copy()).astype(np.float32)/16)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--views',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--method',choices=['sgbm','dlnr'],default='dlnr')
    parser.add_argument('--source',type=Path)
    parser.add_argument('--checkpoint',type=Path)
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--iters',type=int,default=10)
    parser.add_argument('--voxel',type=float,default=.004)
    parser.add_argument('--status-url',default='http://127.0.0.1:8000/api/status',help='Pause CUDA work while an owner app job is active')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    import open3d as o3d
    started=time.monotonic()
    manifest=json.loads((args.views/'views.json').read_text())
    model=None;report={'method':args.method,'views':[],'voxel':args.voxel,'source_sha256':manifest['source_sha256']}
    if args.method=='dlnr':
        import torch
        torch.set_num_threads(4)
        if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
        torch.cuda.reset_peak_memory_stats()
        model=neural_model(args.source,args.checkpoint)
        report['gpu']=torch.cuda.get_device_name(0);report['torch']=torch.__version__
        report['checkpoint_sha256']=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()
    volume=o3d.pipelines.integration.ScalableTSDFVolume(voxel_length=args.voxel,sdf_trunc=args.voxel*5,
                                                      color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    pairs=manifest['pairs'][:args.limit or None]
    for index,pair in enumerate(pairs):
        if model and args.status_url:
            import urllib.request
            while True:
                with urllib.request.urlopen(args.status_url,timeout=10) as response:state=json.load(response)
                if state.get('active_job') is None:break
                print('Waiting for the active app generation before stereo inference…',flush=True)
                time.sleep(5)
        tick=time.monotonic();left,alpha=load_view(args.views/pair['left']['file']);right,_=load_view(args.views/pair['right']['file'])
        cache=args.output/f'{index:03}-disparity.npz'
        if cache.is_file():
            saved=np.load(cache);disparities=[saved['left'],saved['right']]
        else:
            disparities=neural_pair(model,left,right,args.iters) if model else classical_pair(left,right)
            np.savez_compressed(cache,left=disparities[0],right=disparities[1])
        camera=pair['left'];depth,valid=valid_depth(*disparities,alpha,camera['focal'],camera['baseline'])
        np.save(args.output/f'{index:03}-depth.npy',depth)
        if index%6==0:
            scale=np.uint8(np.clip((depth-.75)/1.5*255,0,255));scale[~valid]=0
            Image.fromarray(cv2.applyColorMap(scale,cv2.COLORMAP_TURBO)[...,::-1]).save(args.output/f'{index:03}-depth.png')
        rgbd=o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(np.ascontiguousarray(left)),
                   o3d.geometry.Image(np.ascontiguousarray(depth)),depth_scale=1.,depth_trunc=2.25,convert_rgb_to_intensity=False)
        intrinsic=o3d.camera.PinholeCameraIntrinsic(camera['size'],camera['size'],camera['focal'],camera['focal'],camera['size']/2,camera['size']/2)
        volume.integrate(rgbd,intrinsic,np.asarray(camera['extrinsic']))
        row={'index':index,'valid_pixels':int(valid.sum()),'foreground_pixels':int((alpha>.75).sum()),'seconds':round(time.monotonic()-tick,3)}
        report['views'].append(row);print('STEREO',args.method,index+1,'/',len(pairs),row,flush=True)
    mesh=volume.extract_triangle_mesh();mesh.compute_vertex_normals()
    if not len(mesh.triangles):raise RuntimeError('No stereo surface was recovered')
    o3d.io.write_triangle_mesh(str(args.output/'raw.ply'),mesh)
    mesh.remove_degenerate_triangles();mesh.remove_duplicated_triangles();mesh.remove_unreferenced_vertices()
    o3d.io.write_triangle_mesh(str(args.output/'mesh.ply'),mesh)
    import trimesh
    converted=trimesh.Trimesh(np.asarray(mesh.vertices),np.asarray(mesh.triangles),
                              vertex_colors=np.uint8(np.asarray(mesh.vertex_colors)*255),process=False)
    converted.export(args.output/'mesh.glb')
    report.update(vertices=len(mesh.vertices),triangles=len(mesh.triangles),bounds=converted.bounds.tolist(),seconds=round(time.monotonic()-started,2))
    if model:report['peak_allocated_mib']=round(torch.cuda.max_memory_allocated()/2**20)
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    print('RECONSTRUCTION COMPLETE',json.dumps({k:v for k,v in report.items() if k!='views'}),flush=True)


if __name__=='__main__':main()
