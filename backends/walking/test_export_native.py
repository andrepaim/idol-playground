"""Native regression for actual motion/loop checks across GLB, FBX and Blend."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import bpy
from backends.walking.worker import export, verify_motion


class WalkingExport(unittest.TestCase):
    def test_two_clips_roundtrip_and_wrong_root_distance_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.ops.object.armature_add()
            a = bpy.context.object
            bpy.ops.object.mode_set(mode="EDIT")
            root = a.data.edit_bones[0]
            root.name = "bone_0"
            root.head = (0, 0, 0)
            root.tail = (1, 0, 0)
            paw = a.data.edit_bones.new("bone_14")
            paw.head = (1, 0, 0)
            paw.tail = (1, 0, 1)
            paw.parent = root
            bpy.ops.object.mode_set(mode="OBJECT")
            mesh = bpy.data.meshes.new("triangle")
            mesh.from_pydata([(1, 0, 0), (1, 0, 1), (1, 0.1, 0.5)], [], [(0, 1, 2)])
            obj = bpy.data.objects.new("subject", mesh)
            bpy.context.collection.objects.link(obj)
            obj.parent = a
            group = obj.vertex_groups.new(name="bone_14")
            group.add([0, 1, 2], 1, "REPLACE")
            modifier = obj.modifiers.new("skin", "ARMATURE")
            modifier.object = a
            a.animation_data_create()
            bpy.context.scene.render.fps = 30
            bpy.context.scene.frame_start = 1
            bpy.context.scene.frame_end = 31
            for variant in ("inplace", "forward"):
                action = bpy.data.actions.new("Walk_" + variant)
                action.use_fake_user = True
                a.animation_data.action = action
                for frame in (1, 16, 31):
                    a.pose.bones["bone_0"].location = (0, 0.16 * (frame - 1) / 30 if variant == "forward" else 0, 0)
                    a.pose.bones["bone_14"].rotation_mode = "XYZ"
                    a.pose.bones["bone_14"].rotation_euler = (0.3 if frame == 16 else 0, 0, 0)
                    for b in a.pose.bones:
                        b.keyframe_insert(data_path="location", frame=frame)
                        b.keyframe_insert(data_path="rotation_euler", frame=frame)
            bpy.ops.wm.save_as_mainfile(filepath=str(folder / "character.blend"))
            (folder / "walk-settings.json").write_text(json.dumps({"motion": "inplace"}))
            export(folder, {"motion": "inplace"})
            for variant in ("inplace", "forward"):
                bpy.ops.wm.read_factory_settings(use_empty=True)
                bpy.ops.import_scene.gltf(filepath=str(folder / f"walk-{variant}.glb"))
                imported = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
                action = next(x for x in bpy.data.actions if "Walk_" + variant in x.name)
                imported.animation_data_create()
                imported.animation_data.action = action
                for track in imported.animation_data.nla_tracks:
                    track.mute = True
                verify_motion(imported, 31, 0.16, variant, 0)
                if variant == "forward":
                    with self.assertRaisesRegex(ValueError, "displacement"):
                        verify_motion(imported, 31, 0.8, variant, 0)
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.ops.import_scene.fbx(filepath=str(folder / "animated.fbx"))
            imported = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
            for action in bpy.data.actions:
                imported.animation_data_create()
                imported.animation_data.action = action
                verify_motion(
                    imported, 31, 0.16, "forward" if "forward" in action.name else "inplace", int(action.frame_range[0])
                )
            bpy.ops.wm.open_mainfile(filepath=str(folder / "character.blend"))
            imported = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
            for variant in ("inplace", "forward"):
                imported.animation_data.action = bpy.data.actions["Walk_" + variant]
                verify_motion(imported, 31, 0.16, variant, 1)

    def test_same_endpoint_with_abrupt_last_frame_is_rejected(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.object.armature_add()
        a = bpy.context.object
        a.data.bones[0].name = "bone_0"
        b = a.pose.bones[0]
        b.rotation_mode = "XYZ"
        for frame, angle in ((1, 0), (2, 0.01), (16, 0.1), (30, 1.0), (31, 0)):
            b.rotation_euler = (angle, 0, 0)
            b.keyframe_insert(data_path="rotation_euler", frame=frame)
        bpy.context.scene.render.fps = 30
        with self.assertRaisesRegex(ValueError, "velocity"):
            verify_motion(a, 31, 0.16, "inplace", 1)


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if result.wasSuccessful() else 1)
