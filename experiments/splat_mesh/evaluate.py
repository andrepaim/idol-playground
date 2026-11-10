"""Held-out silhouette checks. Agreement measures fidelity to a splat, not real anatomy."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
import trimesh


def silhouette(vertices,faces,camera):
    camera_points=np.asarray(vertices)@np.asarray(camera['extrinsic'])[:3,:3].T+np.asarray(camera['extrinsic'])[:3,3]
    z=camera_points[:,2]
    pixels=camera_points[:,:2]/np.maximum(z[:,None],1e-6)*camera['focal']+camera['size']/2
    mask=np.zeros((camera['size'],camera['size']),np.uint8)
    for face in faces:
        if np.any(z[face]<=0):continue
        points=np.rint(pixels[face]).clip(-10000,10000).astype(np.int32)
        cv2.fillConvexPoly(mask,points,1)
    return mask.astype(bool)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--views',type=Path,required=True)
    parser.add_argument('--mesh',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((args.views/'views.json').read_text())
    mesh=trimesh.load(args.mesh,force='mesh',process=False)
    rows=[]
    sheet=Image.new('RGB',(1024,8*540),'#eeeeea');draw=ImageDraw.Draw(sheet)
    for index,camera in enumerate(manifest['heldout']):
        rgba=Image.open(args.views/camera['file']).convert('RGBA')
        original=np.asarray(rgba)[...,3]>.75*255
        predicted=silhouette(mesh.vertices,mesh.faces,camera)
        intersection=int((original&predicted).sum());union=int((original|predicted).sum())
        iou=intersection/max(union,1)
        rows.append({'azimuth':camera['azimuth'],'iou':iou,'reference_pixels':int(original.sum()),'mesh_pixels':int(predicted.sum())})
        background=Image.new('RGBA',rgba.size,'#eeeeea');background.alpha_composite(rgba)
        diff=np.zeros((*original.shape,3),np.uint8)+238
        diff[original&predicted]=[80,130,90]
        diff[original&~predicted]=[215,75,65]
        diff[predicted&~original]=[70,100,220]
        sheet.paste(background.convert('RGB'),(0,index*540+28));sheet.paste(Image.fromarray(diff),(512,index*540+28))
        draw.text((12,index*540+6),f'Idol reference | angle {camera["azimuth"]:.1f}',fill='black')
        draw.text((524,index*540+6),f'Overlap {iou:.3f} | green match / red missing / blue excess',fill='black')
    sheet.save(args.output/'silhouette-comparison.png')
    report={'mesh':args.mesh.name,'heldout_views':rows,'mean_iou':float(np.mean([row['iou'] for row in rows])),
            'min_iou':float(min(row['iou'] for row in rows)),'limitation':'Silhouette agreement does not measure interior depth, anatomy or animation topology.'}
    (args.output/'silhouettes.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
