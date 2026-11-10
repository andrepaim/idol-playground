"""CPU Blender walking worker. Only the explicitly reviewed canine profile is supported."""

import argparse
import json
import math
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from walk_motion import CENTERS, PROFILE, foot_path, profile_from_glb, validate_roles


def emit(stage, message, **values):
    print("IDOL_EVENT " + json.dumps({"stage": stage, "message": message, **values}), flush=True)


def prepare(folder, settings):
    from argparse import Namespace
    from experiments.walking.skin import run, collect
    import numpy as np

    if not profile_from_glb((folder / "input.glb").read_bytes())["supported"]:
        raise ValueError("Unsupported canine topology")
    raw, _, _ = collect(folder / "input.glb")
    np.savez(folder / "original.npz", **raw)
    run(
        Namespace(source=folder / "source.fbx", target=folder / "input.glb", output=folder / "skin", smoothing_steps=64)
    )


def pose(folder, settings):
    import bpy
    import numpy as np
    from mathutils import Matrix, Quaternion, Vector
    from experiments.walking.skin import collect
    from experiments.walking.pose import sagittal_rotation

    raw, meshes, a = collect(folder / "skin/corrected.glb")
    # Similarity fitting does not guarantee the reviewed anatomical axes. Reject
    # unsupported orientation instead of silently rotating an unrelated skeleton.
    if np.max(np.abs(np.asarray(a.matrix_world) - np.eye(4))) > 1e-5:
        raise ValueError("This profile requires an identity armature transform (X forward, Z up).")
    head = np.array(a.data.bones["bone_4"].head_local)
    hip = np.array(a.data.bones["bone_0"].head_local)
    if head[0] <= hip[0] or abs(head[1] - hip[1]) > 0.25 * np.linalg.norm(head - hip):
        raise ValueError("The reviewed profile requires X-forward anatomical orientation.")
    height = float(np.ptp(raw["vertices"][:, 2]))
    scale = height / 0.7809345
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Invalid character scale")
    original = np.load(folder / "original.npz")
    # GLB exporters can reorder/split vertices. Map anatomical masks by position.
    from scipy.spatial import cKDTree

    distance, order = cKDTree(original["vertices"]).query(raw["vertices"])
    if distance.max() > height * 1e-5:
        raise ValueError("Skin correction changed geometry")
    original_names = list(original["names"])
    names = list(raw["names"])
    anatomical = original["weights"][order][:, [original_names.index(n) for n in names]]
    np.savez(
        folder / "surface.npz", vertices=raw["vertices"], weights=raw["weights"], anatomical=anatomical, names=names
    )
    for b in a.pose.bones:
        basis = b.matrix_basis.copy()
        b.rotation_mode = "QUATERNION"
        b.matrix_basis = basis
    held = set(range(3, 20))
    angles = {i: angle for start in (22, 28) for i, angle in zip(range(start, start + 6), (-50, -115, -60, -80, 0, 0))}
    for b in a.pose.bones:
        i = int(b.name[5:])
        if i not in (0, 1, 2) and i not in held and i not in angles:
            continue
        rest = b.bone.tail_local - b.bone.head_local
        if i == 0:
            rest = a.data.bones["bone_2"].head_local - b.bone.head_local
        angle = (
            0
            if i in held
            else sagittal_rotation(
                rest, (math.cos(math.radians(angles.get(i, 0))), 0, math.sin(math.radians(angles.get(i, 0))))
            )
        )
        q = Quaternion(Vector((0, 1, 0)), angle) @ b.bone.matrix_local.to_quaternion()
        b.matrix = Matrix.LocRotScale(b.head.copy(), q, Vector((1, 1, 1)))
        bpy.context.view_layer.update()
    root = a.pose.bones["bone_0"]
    m = root.matrix.copy()
    m.translation.z -= 0.02 * scale
    root.matrix = m
    bpy.context.view_layer.update()
    saved = {b.name: b.matrix_basis.copy() for b in a.pose.bones}
    contacts = {}
    for role, name in settings["paws"].items():
        region = raw["vertices"][anatomical[:, names.index(name)] > 0.4]
        if len(region) < 8:
            raise ValueError("Paw region is too small for reliable contact")
        contacts[name] = region[region[:, 2] <= np.quantile(region[:, 2], 0.2)].mean(0)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.mode_set(mode="EDIT")
    for name, position in contacts.items():
        b = a.data.edit_bones.new("contact-" + name)
        b.parent = a.data.edit_bones[name]
        b.head = b.parent.tail
        b.tail = position
        b.use_connect = True
        b.use_deform = False
    bpy.ops.object.mode_set(mode="POSE")
    for name, basis in saved.items():
        a.pose.bones[name].matrix_basis = basis
    ground = float(hip[2] - 0.458 * scale)
    anchors = {}
    for role, name in settings["paws"].items():
        # Reviewed asymmetric stance from the accepted trial, scaled with body.
        x, y = {"bone_14": (0.30, 0.01), "bone_19": (0.29, -0.15), "bone_27": (-0.12, 0.16), "bone_33": (-0.12, -0.16)}[
            name
        ]
        anchors[role] = [float(hip[0] + (x + 0.065) * scale), y * scale, ground]
        marker = bpy.data.objects.new("paw-" + name, None)
        bpy.context.collection.objects.link(marker)
        marker.location = anchors[role]
        b = a.pose.bones["contact-" + name]
        c = b.constraints.new("IK")
        c.target = marker
        c.use_tail = True
        c.chain_count = 6 if role.startswith("fore") else 7
        c.use_stretch = False
        c.iterations = 500
        b.lock_ik_x = b.lock_ik_y = b.lock_ik_z = True
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()
    (folder / "calibration.json").write_text(json.dumps({"scale": scale, "ground": ground, "anchors": anchors}))
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "working.blend"))


def bake(folder, settings):
    import bpy
    import numpy as np
    from mathutils import Vector

    bpy.ops.wm.open_mainfile(filepath=str(folder / "working.blend"))
    a = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    raw = np.load(folder / "surface.npz")
    names = list(raw["names"])
    calibration = json.loads((folder / "calibration.json").read_text())
    scale = calibration["scale"]
    ground = calibration["ground"]
    stride = (0.16 if settings["speed"] == "relaxed" else 0.18) * scale
    frames = 48 if settings["speed"] == "relaxed" else 36
    base = {n: a.pose.bones[n].matrix_basis.copy() for n in names}
    base_root = a.pose.bones["bone_0"].matrix.copy()
    inverse = np.array([np.array(a.data.bones[n].matrix_local.inverted()) for n in names])
    paw_data = []
    roles = list(settings["paws"])
    for role in roles:
        name = settings["paws"][role]
        ids = np.where(raw["anatomical"][:, names.index(name)] > 0.4)[0]
        region = raw["vertices"][ids]
        low = region[:, 2] <= np.quantile(region[:, 2], 0.2)
        w = raw["weights"][ids]
        j = np.argsort(-w, axis=1)[:, :4]
        w4 = np.take_along_axis(w, j, axis=1)
        paw_data.append((j, w4, np.column_stack((region, np.ones(len(region)))), low))

    def actual_contacts():
        matrices = np.array([np.array(a.pose.bones[n].matrix) for n in names]) @ inverse
        points = []
        minimum = []
        for j, w, hom, low in paw_data:
            vertices = np.einsum("nkij,nj,nk->ni", matrices[j], hom, w)[:, :3]
            point = vertices[low].mean(0)
            # Pin the lowest selected surface point, avoiding the trial's
            # quantile-based penetration. This still measures selected paw ROIs.
            point[2] = vertices[:, 2].min()
            points.append(point)
            minimum.append(point[2])
        return np.asarray(points), minimum

    baked = []
    surfaces = []
    flags_record = []
    errors = []
    for i in range(frames + 1):
        phase = i / frames
        for n in names:
            a.pose.bones[n].matrix_basis = base[n]
        m = base_root.copy()
        m.translation.z += 0.0025 * scale * math.sin(4 * math.pi * phase)
        a.pose.bones["bone_0"].matrix = m
        desired = []
        flags = []
        for role in roles:
            dx, dz, stance = foot_path(
                phase, CENTERS[role], stride, (0.045 if role.startswith("fore") else 0.04) * scale
            )
            point = np.array(calibration["anchors"][role]) + [dx, 0, dz]
            bpy.data.objects["paw-" + settings["paws"][role]].location = point
            desired.append(point)
            flags.append(stance)
        bpy.context.view_layer.update()
        for _ in range(20):
            actual, _ = actual_contacts()
            difference = np.asarray(desired) - actual
            if np.linalg.norm(difference, axis=1).max() < 0.0005 * scale:
                break
            for k, role in enumerate(roles):
                marker = bpy.data.objects["paw-" + settings["paws"][role]]
                marker.location += Vector(np.clip(difference[k] * 0.85, -0.03 * scale, 0.03 * scale))
            bpy.context.view_layer.update()
        actual, _ = actual_contacts()
        surfaces.append(actual)
        flags_record.append(flags)
        errors.append(np.linalg.norm(np.asarray(desired) - actual, axis=1))
        matrices = {b.name: b.matrix.copy() for b in a.pose.bones}
        poses = []
        for j, n in enumerate(names):
            b = a.pose.bones[n]
            matrix = b.bone.matrix_local.inverted() @ matrices[n]
            if b.parent:
                matrix = (
                    b.bone.matrix_local.inverted()
                    @ b.parent.bone.matrix_local
                    @ matrices[b.parent.name].inverted()
                    @ matrices[n]
                )
            loc, rot, scl = matrix.decompose()
            if baked and np.dot(rot[:], baked[-1][j][1]) < 0:
                rot.negate()
            poses.append((loc[:], rot[:], scl[:]))
        baked.append(poses)
        emit("walk_bake", f"Solving paw contact · frame {i + 1} of {frames + 1}", step=i + 1, total_steps=frames + 1)
    errors = np.array(errors)
    surfaces = np.array(surfaces)
    flags = np.array(flags_record)
    penetration = float(np.maximum(0, ground - surfaces[:, :, 2])[flags].max())
    world = surfaces.copy()
    world[:, :, 0] += np.linspace(0, stride, frames + 1)[:, None]
    stance_pairs = flags[:-1] & flags[1:]
    slide = float(np.linalg.norm(np.diff(world[:, :, :2], axis=0), axis=2)[stance_pairs].max())
    if errors.max() > 0.008 * scale or penetration > 0.003 * scale or slide > 0.006 * scale:
        raise ValueError(
            f"Paw contact validation failed: error={errors.max():.5f}, penetration={penetration:.5f}, slide/frame={slide:.5f}"
        )
    for b in a.pose.bones:
        for c in list(b.constraints):
            b.constraints.remove(c)
    for o in list(bpy.data.objects):
        if o.name.startswith("paw-"):
            bpy.data.objects.remove(o, do_unlink=True)
    a.animation_data_create()
    bpy.context.scene.render.fps = 30
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = frames + 1
    for variant in ("inplace", "forward"):
        action = bpy.data.actions.new("Walk_" + variant)
        action.use_fake_user = True
        a.animation_data.action = action
        for j, n in enumerate(names):
            b = a.pose.bones[n]
            for k, channel in enumerate(("location", "rotation_quaternion", "scale")):
                values = np.array([p[j][k] for p in baked])
                if variant == "forward" and n == "bone_0" and channel == "location":
                    for i in range(frames + 1):
                        values[i] += np.array(
                            b.bone.matrix_local.to_3x3().inverted() @ Vector((stride * i / frames, 0, 0))
                        )
                for component in range(values.shape[1]):
                    curve = action.fcurves.new(b.path_from_id(channel), index=component, action_group=n)
                    curve.keyframe_points.add(frames + 1)
                    curve.keyframe_points.foreach_set(
                        "co", np.column_stack((np.arange(1, frames + 2), values[:, component])).ravel()
                    )
                    for key in curve.keyframe_points:
                        key.interpolation = "LINEAR"
                    curve.update()
    for action in list(bpy.data.actions):
        if action.name not in ("Walk_inplace", "Walk_forward"):
            bpy.data.actions.remove(action)
    a.animation_data.action = bpy.data.actions["Walk_" + settings["motion"]]
    a.update_tag(refresh={"TIME"})
    bpy.context.scene.frame_set(0)
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "character.blend"))
    report = {
        "profile": PROFILE,
        "duration": frames / 30,
        "frames": frames + 1,
        "stride": stride,
        "ground_z": ground,
        "max_contact_error": float(errors.max()),
        "max_stance_penetration": penetration,
        "max_stance_slide_per_frame": slide,
        "paws": settings["paws"],
        "speed": settings["speed"],
        "motion": settings["motion"],
        "warnings": [
            "Experimental canine walk. Inspect hind-leg deformation and paw contact before use. Generic mapping and game-engine validation remain open."
        ],
        "contact_scope": "Lowest point and rest-low-patch centroid of four selected paw regions; not whole-mesh collision validation.",
        "provenance": "Procedural four-beat lateral walk; conservative lift/stride informed by the previous local recorded-motion trial. No capture file is bundled.",
    }
    (folder / "walk.json").write_text(json.dumps(report, indent=2))


def export(folder, settings):
    import bpy
    import shutil

    bpy.ops.wm.open_mainfile(filepath=str(folder / "character.blend"))
    a = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    for variant in ("inplace", "forward"):
        a.animation_data.action = bpy.data.actions["Walk_" + variant]
        a.update_tag(refresh={"TIME"})
        bpy.context.scene.frame_set(0)
        bpy.context.scene.frame_set(1)
        bpy.ops.export_scene.gltf(
            filepath=str(folder / f"walk-{variant}.glb"),
            export_format="GLB",
            export_animations=True,
            export_frame_range=True,
            export_force_sampling=True,
            export_animation_mode="ACTIVE_ACTIONS",
            export_anim_single_armature=False,
            export_anim_slide_to_zero=True,
            export_nla_strips_merged_animation_name="Walk_" + variant,
        )
    shutil.copy2(folder / f"walk-{settings['motion']}.glb", folder / "animated.glb")
    bpy.ops.export_scene.fbx(
        filepath=str(folder / "animated.fbx"),
        object_types={"ARMATURE", "MESH"},
        add_leaf_bones=False,
        bake_anim=True,
        bake_anim_use_all_actions=True,
        bake_anim_use_nla_strips=False,
        bake_anim_simplify_factor=0,
        path_mode="COPY",
        embed_textures=True,
    )


def verify_motion(a, frames, stride, variant, start):
    """Check evaluated matrices, including rotation at the loop boundary."""
    import bpy
    import numpy as np

    snapshots = []
    span = (frames - 1) / 30 * bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    step = span / (frames - 1)
    for frame in (start, start + step, start + span / 2, start + span - step, start + span):
        bpy.context.scene.frame_set(int(frame), subframe=frame - int(frame))
        bpy.context.view_layer.update()
        snapshots.append(
            np.array([np.array(a.matrix_world @ b.matrix) for b in a.pose.bones if b.name.startswith("bone_")])
        )
    delta = snapshots[-1][:, :3, 3] - snapshots[0][:, :3, 3]
    expected = np.array([stride if variant == "forward" else 0, 0, 0])
    error = float(np.max(np.abs(delta - expected)))
    rotation_error = float(np.max(np.abs(snapshots[-1][:, :3, :3] - snapshots[0][:, :3, :3])))
    if error > max(0.001, stride * 0.005) or rotation_error > 0.001:
        raise ValueError("Exported root/loop displacement or rotation differs from the baked walk")
    if np.max(np.abs(snapshots[2] - snapshots[0])) < 0.001:
        raise ValueError("Exported walk has no evaluated motion")
    # Finite differences at 30 Hz are an approximation to endpoint velocity.
    # Check rotation separately from translations, which depend on model scale.
    jump = (snapshots[1] - snapshots[0]) - (snapshots[-1] - snapshots[-2])
    rotation_jump = float(np.max(np.abs(jump[:, :3, :3])))
    translation_jump = float(np.max(np.abs(jump[:, :3, 3])))
    if rotation_jump > 0.08 or translation_jump > stride * 0.1:
        raise ValueError("Exported loop has an abrupt endpoint velocity change")
    return {
        "loop_displacement_error": error,
        "loop_rotation_error": rotation_error,
        "loop_rotation_frame_delta_error": rotation_jump,
        "loop_translation_frame_delta_error": translation_jump,
    }


def exported_contacts(raw, a, folder, report, variant):
    import bpy
    import numpy as np
    from scipy.spatial import cKDTree

    original = np.load(folder / "surface.npz")
    distance, order = cKDTree(original["vertices"]).query(raw["vertices"])
    scale = report["stride"] / (0.16 if report["speed"] == "relaxed" else 0.18)
    if distance.max() > scale * 1e-5:
        raise ValueError("Export changed the rest geometry")
    names = raw["names"]
    inverse = np.array([np.array((a.matrix_world @ a.data.bones[n].matrix_local).inverted()) for n in names])
    paw_data = []
    roles = list(report["paws"])
    for role in roles:
        anatomical = original["anatomical"][order, list(original["names"]).index(report["paws"][role])]
        ids = np.where(anatomical > 0.4)[0]
        region = raw["vertices"][ids]
        low = region[:, 2] <= np.quantile(region[:, 2], 0.2)
        w = raw["weights"][ids]
        j = np.argsort(-w, axis=1)[:, :4]
        w4 = np.take_along_axis(w, j, axis=1)
        paw_data.append((j, w4, np.column_stack((region, np.ones(len(region)))), low))
    contacts = []
    flags = []
    for frame in range(report["frames"]):
        sample = frame / 30 * bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
        bpy.context.scene.frame_set(int(sample), subframe=sample - int(sample))
        bpy.context.view_layer.update()
        matrices = np.array([np.array(a.matrix_world @ a.pose.bones[n].matrix) for n in names]) @ inverse
        points = []
        stance = []
        for role, (j, w, hom, low) in zip(roles, paw_data):
            v = np.einsum("nkij,nj,nk->ni", matrices[j], hom, w)[:, :3]
            p = v[low].mean(0)
            p[2] = v[:, 2].min()
            points.append(p)
            stance.append(foot_path(frame / (report["frames"] - 1), CENTERS[role], report["stride"], 0.04 * scale)[2])
        contacts.append(points)
        flags.append(stance)
    contacts = np.asarray(contacts)
    flags = np.asarray(flags)
    penetration = float(np.maximum(0, report["ground_z"] - contacts[:, :, 2])[flags].max())
    if variant == "inplace":
        contacts[:, :, 0] += np.linspace(0, report["stride"], report["frames"])[:, None]
    slide = float(np.linalg.norm(np.diff(contacts[:, :, :2], axis=0), axis=2)[flags[:-1] & flags[1:]].max())
    if penetration > 0.003 * scale or slide > 0.006 * scale:
        raise ValueError(
            f"Exported skin failed paw contact/sliding checks: penetration={penetration}, slide={slide}, scale={scale}"
        )
    return {"stance_penetration": penetration, "stance_slide_per_frame": slide}


def verify(folder, settings):
    import bpy
    from experiments.walking.skin import collect

    report = json.loads((folder / "walk.json").read_text())
    results = {}
    expected_vertices = len(__import__("numpy").load(folder / "surface.npz")["vertices"])

    def appearance(a):
        meshes = [
            o
            for o in bpy.context.scene.objects
            if o.type == "MESH" and any(m.type == "ARMATURE" and m.object == a for m in o.modifiers)
        ]
        if sum(len(o.data.vertices) for o in meshes) != expected_vertices:
            raise ValueError("Export changed vertex count")
        if not all(o.data.color_attributes or o.data.uv_layers for o in meshes):
            raise ValueError("Export lost appearance attributes")
        if not all(all(v.groups for v in o.data.vertices) for o in meshes):
            raise ValueError("Export lost skin weights")

    for variant in ("inplace", "forward"):
        raw, meshes, a = collect(folder / f"walk-{variant}.glb")
        actions = [x for x in bpy.data.actions if "Walk_" + variant in x.name]
        if len(actions) != 1:
            raise ValueError("Missing or ambiguous exported walk action")
        a.animation_data_create()
        a.animation_data.action = actions[0]
        result = verify_motion(a, report["frames"], report["stride"], variant, 0)
        result.update(exported_contacts(raw, a, folder, report, variant))
        appearance(a)
        results[variant] = {"vertices": len(raw["vertices"]), "bones": len(raw["names"]), **result}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(folder / "animated.fbx"))
    a = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    actions = [x for x in bpy.data.actions if "Walk_" in x.name]
    if len(actions) != 2:
        raise ValueError("FBX must retain both walking clips")
    appearance(a)
    for action in actions:
        a.animation_data_create()
        a.animation_data.action = action
        verify_motion(
            a,
            report["frames"],
            report["stride"],
            "forward" if "forward" in action.name else "inplace",
            int(action.frame_range[0]),
        )
    bpy.ops.wm.open_mainfile(filepath=str(folder / "character.blend"))
    a = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    appearance(a)
    for variant in ("inplace", "forward"):
        if "Walk_" + variant not in bpy.data.actions:
            raise ValueError("Blend lost walk action")
        a.animation_data.action = bpy.data.actions["Walk_" + variant]
        verify_motion(a, report["frames"], report["stride"], variant, 1)
    report["verification"] = results
    report["fbx_clips"] = len(actions)
    (folder / "walk.json").write_text(json.dumps(report, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", required=True)
    p.add_argument("--job", type=Path, required=True)
    args = p.parse_args()
    folder = args.job.resolve()
    settings = json.loads((folder / "walk-settings.json").read_text())
    validate_roles(settings["paws"], settings["reviewed"])
    {"walk_prepare": prepare, "walk_pose": pose, "walk_bake": bake, "walk_export": export, "walk_verify": verify}[
        args.phase
    ](folder, settings)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("IDOL_EVENT " + json.dumps({"event": "error", "message": str(error)}), flush=True)
        traceback.print_exc()
        code = 1
    else:
        code = 0
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
