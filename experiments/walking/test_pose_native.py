"""Native regression: rest-only GLB input and orphan BVH actions must export the posed clip."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from argparse import Namespace

import bpy
from experiments.walking.pose import run


class PoseRoundTrip(unittest.TestCase):
    def test_static_input_exports_only_the_requested_pose(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.ops.object.armature_add()
            armature=bpy.context.object
            bpy.ops.object.mode_set(mode='EDIT')
            hips=armature.data.edit_bones[0];hips.name='hips';hips.head=(0,0,0);hips.tail=(1,0,0)
            leg=armature.data.edit_bones.new('leg');leg.head=(1,0,0);leg.tail=(1,0,1);leg.parent=hips
            bpy.ops.object.mode_set(mode='OBJECT')
            mesh=bpy.data.meshes.new('triangle');mesh.from_pydata([(1,0,0),(1,0,1),(1,.1,.5)],[],[(0,1,2)])
            obj=bpy.data.objects.new('subject',mesh);bpy.context.collection.objects.link(obj);obj.parent=armature
            group=obj.vertex_groups.new(name='leg');group.add([0,1,2],1,'REPLACE')
            modifier=obj.modifiers.new('skin','ARMATURE');modifier.object=armature
            bpy.ops.export_scene.gltf(filepath=str(root/'input.glb'),export_format='GLB',export_animations=False)
            (root/'reference.bvh').write_text('''HIERARCHY
ROOT Hips
{
 OFFSET 0 0 0
 CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
 JOINT Chest
 {
  OFFSET 1 0 0
  CHANNELS 3 Zrotation Xrotation Yrotation
  End Site
  {
   OFFSET 1 0 0
  }
 }
}
MOTION
Frames: 2
Frame Time: 0.0333333333
0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0
''')
            (root/'mapping.json').write_text(json.dumps({'source_hips':'Hips','source_chest':'Chest','target_hips':'hips','target_chest':'leg','joints':[{'target':'hips','source':'Hips','hold':True},{'target':'leg','source':'Chest','degrees':0}]}))
            run(Namespace(input=root/'input.glb',motion=root/'reference.bvh',mapping=root/'mapping.json',frame=1,output=root/'result'))
            blob=(root/'result/pose.glb').read_bytes();length=struct.unpack_from('<I',blob,12)[0];document=json.loads(blob[20:20+length])
            self.assertEqual([a['name'] for a in document['animations']],['Standing feasibility'])
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.ops.import_scene.gltf(filepath=str(root/'result/pose.glb'))
            a=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
            actions=[strip.action for track in a.animation_data.nla_tracks for strip in track.strips]
            if a.animation_data.action:actions.append(a.animation_data.action)
            self.assertTrue(actions)
            a.animation_data.action=actions[0]
            for track in a.animation_data.nla_tracks:track.mute=True
            bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
            ob=next(o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers))
            evaluated=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());data=evaluated.to_mesh()
            points=[evaluated.matrix_world@v.co for v in data.vertices]
            self.assertAlmostEqual(max(v.x for v in points),2,places=4)
            self.assertAlmostEqual(max(abs(v.z) for v in points),0,places=4)
            evaluated.to_mesh_clear()


if __name__=='__main__':
    result=unittest.main(exit=False).result
    sys.stdout.flush();sys.stderr.flush();os._exit(0 if result.wasSuccessful() else 1)
