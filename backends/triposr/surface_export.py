"""Preserve geometry normals when UV unwrapping splits shared vertices."""
import trimesh
from trimesh.visual import TextureVisuals
from trimesh.visual.material import PBRMaterial


def textured_mesh(mesh, atlas, texture):
    visual = TextureVisuals(uv=atlas['uvs'], material=PBRMaterial(
        baseColorTexture=texture, metallicFactor=0, roughnessFactor=1))
    return trimesh.Trimesh(vertices=mesh.vertices[atlas['vmapping']], faces=atlas['indices'],
                           vertex_normals=mesh.vertex_normals[atlas['vmapping']],
                           visual=visual, process=False)
