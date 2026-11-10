"""Run in the isolated experiment environment; checks its real GLB encoder."""
import io
import json
import struct
import unittest
import numpy as np
import trimesh
from refine import appearance_glb


class AppearanceExport(unittest.TestCase):
    def test_rgb_is_linear_float_unlit_and_geometry_survives_roundtrip(self):
        mesh=trimesh.Trimesh([[0,0,0],[1,0,0],[0,1,0]],[[0,1,2]],
                             vertex_colors=[[255,128,0,255]]*3,process=False)
        data=appearance_glb(mesh)
        self.assertEqual(struct.unpack_from('<I',data,8)[0],len(data))
        length=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+length]);binary=data[28+length:]
        attributes=doc['meshes'][0]['primitives'][0]['attributes'];accessor=doc['accessors'][attributes['COLOR_0']]
        self.assertEqual(accessor['componentType'],5126)
        self.assertNotIn('normalized',accessor)
        view=doc['bufferViews'][accessor['bufferView']]
        rgba=struct.unpack_from('<4f',binary,view['byteOffset'])
        self.assertAlmostEqual(rgba[0],1)
        self.assertAlmostEqual(rgba[1],((128/255+.055)/1.055)**2.4,places=6)
        self.assertAlmostEqual(rgba[2],0)
        self.assertAlmostEqual(rgba[3],1)
        self.assertIn('KHR_materials_unlit',doc['materials'][0]['extensions'])
        scene=trimesh.load(io.BytesIO(data),file_type='glb',force='scene',process=False)
        geometry=next(iter(scene.geometry.values()))
        self.assertEqual(len(geometry.faces),1)
        np.testing.assert_allclose(geometry.bounds,mesh.bounds)


if __name__=='__main__':unittest.main()
