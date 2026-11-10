import unittest
import numpy as np
import torch


class SurfaceTests(unittest.TestCase):
    def test_cpu_surface_preserves_axis_order_for_upstream_helper(self):
        from torchmcubes import marching_cubes
        field=np.full((10,14,18),-1,dtype=np.float32)
        field[2:6,5:10,10:16]=1
        vertices, faces=marching_cubes(torch.from_numpy(field),0)
        normalized=vertices.numpy()[:,[2,1,0]]
        np.testing.assert_allclose(normalized.min(axis=0),[1.5,4.5,9.5])
        np.testing.assert_allclose(normalized.max(axis=0),[5.5,9.5,15.5])
        self.assertTrue(len(faces)>0)

    def test_empty_density_is_actionable(self):
        from torchmcubes import marching_cubes
        with self.assertRaisesRegex(ValueError,'surface'):
            marching_cubes(torch.ones((8,8,8)),0)


class ExportNormalsTests(unittest.TestCase):
    def test_uv_splits_preserve_smooth_normals_after_roundtrip(self):
        import io
        import trimesh
        from PIL import Image
        from surface_export import textured_mesh
        mesh=trimesh.creation.icosphere(subdivisions=0)
        faces=mesh.faces.copy()
        face,corner=np.argwhere(faces==0)[0]
        faces[face,corner]=len(mesh.vertices)
        mapping=np.r_[np.arange(len(mesh.vertices)),0]
        atlas={'vmapping':mapping,'indices':faces,'uvs':np.zeros((len(mapping),2))}
        result=textured_mesh(mesh,atlas,Image.new('RGB',(4,4),'red'))
        np.testing.assert_allclose(result.vertex_normals[0],result.vertex_normals[-1],atol=1e-6)
        scene=trimesh.load(io.BytesIO(result.export(file_type='glb')),file_type='glb',force='scene',process=False)
        loaded=next(iter(scene.geometry.values()))
        np.testing.assert_allclose(loaded.vertex_normals[0],loaded.vertex_normals[-1],atol=1e-6)
