import json
import math
import struct

import pytest

from experiments.vertical_slice.quadruped_fit import (
    AnatomyError, apply_matrix, canonicalize, fit_quadruped, foot_clusters, glb_skin_report,
    landmarks, limb_centerline, planted_paw_path, stride_from_contact, tail_centerline,
)

# A voxel "box dog" in the canonical frame: +Z up, head toward -Y, left side +X, floor z=0.
LEGS = {'fore_left': (2, -12), 'fore_right': (-5, -12), 'hind_left': (2, 9), 'hind_right': (-5, 9)}


def box_dog(leg_height=12, with_tail=True, legs=LEGS):
    cells = set()

    def fill(x0, x1, y0, y1, z0, z1):
        cells.update((x, y, z) for x in range(x0, x1) for y in range(y0, y1) for z in range(z0, z1))

    for x, y in legs.values():
        fill(x, x + 3, y, y + 3, 0, leg_height)
    top = leg_height + 8
    fill(-5, 5, -14, 14, leg_height, top)                 # torso
    fill(-3, 3, -22, -12, top - 2, top + 8)               # neck and head, forward and up
    if with_tail:
        fill(-1, 1, 14, 20, top - 2, top)                 # tail runs back...
        fill(-1, 1, 18, 20, top, top + 7)                 # ...then curls up
    return voxel_surface(cells)


def voxel_surface(cells):
    """Welded surface mesh of a voxel union, so touching boxes form one connected surface."""
    index, vertices, triangles = {}, [], []

    def vertex(p):
        if p not in index:
            index[p] = len(vertices)
            vertices.append(tuple(float(v) for v in p))
        return index[p]

    for x, y, z in cells:
        for axis in range(3):
            for side in (0, 1):
                n = [x, y, z]
                n[axis] += 1 if side else -1
                if tuple(n) in cells:
                    continue
                u, v = [a for a in range(3) if a != axis]
                corners = []
                for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    c = [x, y, z]
                    c[axis] += side
                    c[u] += du
                    c[v] += dv
                    corners.append(vertex(tuple(c)))
                triangles += [(corners[0], corners[1], corners[2]), (corners[0], corners[2], corners[3])]
    return vertices, triangles


def rotate_z(points, angle, offset=(0.0, 0.0, 0.0)):
    c, s = math.cos(angle), math.sin(angle)
    return [(c * x - s * y + offset[0], s * x + c * y + offset[1], z + offset[2]) for x, y, z in points]


@pytest.mark.parametrize('angle', [0.0, math.pi, math.pi / 2, -2.3])
def test_canonicalize_puts_head_toward_minus_y_and_floor_at_zero(angle):
    points, triangles = box_dog()
    moved = rotate_z(points, angle, (7.0, -3.0, 2.5))
    matrix, report = canonicalize(moved)
    canonical = [apply_matrix(matrix, p) for p in moved]
    assert min(p[2] for p in canonical) == pytest.approx(0, abs=1e-9)
    head = max(canonical, key=lambda p: p[2])          # head top (z=28) is above the tail curl (z=27)
    assert head[1] < -10, 'the tall head block must end up toward -Y'
    assert report['length'] == pytest.approx(42, abs=1.5)
    # Left legs must stay left (+X): canonicalization is a proper rotation, never a mirror.
    feet = foot_clusters(canonical, triangles)
    assert feet['fore_left']['center'][0] > feet['fore_right']['center'][0]


def test_canonicalize_rejects_degenerate_input():
    with pytest.raises(ValueError):
        canonicalize([(0, 0, 0), (1, 0, 0)])
    with pytest.raises(ValueError):
        canonicalize([(0, 0, 0), (1, 0, float('nan')), (0, 1, 1), (1, 1, 1)])


def test_foot_clusters_label_four_paws():
    feet = foot_clusters(*box_dog())
    assert set(feet) == set(LEGS)
    for name, (x, y) in LEGS.items():
        cx, cy, _ = feet[name]['center']
        assert cx == pytest.approx(x + 1.5, abs=0.6) and cy == pytest.approx(y + 1.5, abs=0.6)


def test_foot_clusters_sample_triangles_of_sparse_paws():
    # Grid cells smaller than the vertex spacing split vertex-only paws; face sampling keeps them whole.
    points, triangles = box_dog()
    sparse = [(x * 1.7, y * 1.7, z) for x, y, z in points]
    with pytest.raises(AnatomyError):
        foot_clusters(sparse)
    assert set(foot_clusters(sparse, triangles)) == set(LEGS)


def test_foot_clusters_reject_missing_or_fused_legs():
    three = {k: v for k, v in LEGS.items() if k != 'hind_right'}
    with pytest.raises(AnatomyError, match='4 separate paws'):
        foot_clusters(*box_dog(legs=three))
    fused = dict(LEGS, fore_right=(0, -12))                 # touches fore_left: one blob
    with pytest.raises(AnatomyError):
        foot_clusters(*box_dog(legs=fused))


def test_limb_centerline_follows_the_leg_and_freezes_inside_the_torso():
    points, triangles = box_dog()
    feet = foot_clusters(points, triangles)
    line = limb_centerline(points, feet['hind_left']['center'], top=18, step=1.0, radius=2.6)
    for x, y, z in line:
        assert x == pytest.approx(3.5, abs=0.6) and y == pytest.approx(10.5, abs=0.6)
    assert line[0][2] < 1 and line[-1][2] >= 17


def test_tail_centerline_runs_from_base_to_tip():
    points, triangles = box_dog()
    marks = landmarks(points, triangles)
    line = tail_centerline(points, triangles, marks)
    assert line is not None
    tip = line[-1]
    assert tip[1] > 17 and tip[2] > 24, tip
    assert line[0][1] < tip[1] or line[0][2] < tip[2]
    tailless = box_dog(with_tail=False)
    assert tail_centerline(*tailless, landmarks(*tailless)) is None


SPEC = {
    'spine': ['hip', 'chest', 'head'],
    'legs': {'fore_left': ['fl_top', 'fl_paw'], 'hind_left': ['hl_top', 'hl_paw'],
             'fore_right': ['fr_top', 'fr_paw'], 'hind_right': ['hr_top', 'hr_paw']},
    'tail': ['tail_base', 'tail_mid'],
}


def template_joints(leg_height=12):
    top = leg_height + 8
    j = {'hip': (0, 10.5, top - 3), 'chest': (0, -10.5, top - 3), 'head': (0, -18, top + 3),
         'tail_base': (0, 14, top - 1), 'tail_mid': (0, 19, top + 2)}
    for name, (x, y) in LEGS.items():
        prefix = ''.join(w[0] for w in name.split('_'))
        j[f'{prefix}_top'] = (x + 1.5, y + 1.5, top - 3)
        j[f'{prefix}_paw'] = (x + 1.5, y + 1.5, 0.5)
    return j


def test_fit_moves_template_joints_into_a_differently_proportioned_body():
    template = box_dog()
    target_points, target_triangles = box_dog(leg_height=20)          # taller legs, same layout
    fitted = fit_quadruped(template_joints(), landmarks(*template), target_points,
                           target_triangles, landmarks(target_points, target_triangles), SPEC,
                           template_points=template[0])
    assert set(fitted['joints']) == set(template_joints())
    for name, (x, y) in LEGS.items():
        prefix = ''.join(w[0] for w in name.split('_'))
        for joint in (f'{prefix}_top', f'{prefix}_paw'):
            jx, jy, _ = fitted['joints'][joint]
            assert x - .2 <= jx <= x + 3.2 and y - .2 <= jy <= y + 3.2, (joint, fitted['joints'][joint])
    assert fitted['joints']['fl_top'][2] > 20 > fitted['joints']['fl_paw'][2]
    assert fitted['joints']['fl_paw'][2] == pytest.approx(0.15 * fitted['joints']['fl_top'][2])  # above the sole
    assert fitted['joints']['hip'][2] == pytest.approx(25, abs=0.5)    # same place in the torso section
    assert fitted['joints']['head'][1] < -12
    assert fitted['tail_found'] is True
    assert fitted['joints']['tail_mid'][2] > fitted['joints']['tail_base'][2]


def test_fit_mirrors_shoulder_and_hip_sockets_when_standing_legs_are_asymmetric():
    template = box_dog()
    staggered = dict(LEGS, hind_left=(2, 7))                        # one hind leg stands further forward
    target_points, target_triangles = box_dog(legs=staggered)
    fitted = fit_quadruped(template_joints(), landmarks(*template), target_points, target_triangles,
                           landmarks(target_points, target_triangles), SPEC, template_points=template[0])
    left, right = fitted['joints']['hl_top'], fitted['joints']['hr_top']
    assert left[0] == pytest.approx(-right[0]) and left[1:] == pytest.approx(right[1:])
    assert fitted['joints']['hl_paw'][1] < fitted['joints']['hr_paw'][1]   # paws keep their own positions


def test_fit_falls_back_to_back_height_when_template_sections_are_too_sparse():
    template = box_dog()
    target_points, target_triangles = box_dog(leg_height=20)
    sparse = [p for p in template[0] if abs(p[0]) > 2]                 # no midline samples at all
    fitted = fit_quadruped(template_joints(), landmarks(*template), target_points, target_triangles,
                           landmarks(target_points, target_triangles), SPEC, template_points=sparse)
    assert all(math.isfinite(v) for joint in fitted['joints'].values() for v in joint)
    assert fitted['joints']['hip'][2] == pytest.approx(17 * 28 / 20)     # back-height ratio fallback


def test_fit_without_tail_collapses_tail_chain_and_reports_it():
    template = box_dog()
    target_points, target_triangles = box_dog(with_tail=False)
    fitted = fit_quadruped(template_joints(), landmarks(*template), target_points,
                           target_triangles, landmarks(target_points, target_triangles), SPEC)
    assert fitted['tail_found'] is False
    assert 'tail' in ' '.join(fitted['warnings'])


def test_stride_from_contact_recovers_body_speed():
    duration, speed, duty = 1.0, 0.8, 0.6
    frames = 60
    forward, height = [], []
    for i in range(frames):
        phase = i / frames
        if phase < duty:                                  # planted: moves backward at body speed
            forward.append(0.24 - speed * phase * duration)
            height.append(0.0)
        else:                                             # swing: returns forward in the air
            swing = (phase - duty) / (1 - duty)
            forward.append(0.24 - speed * duty * duration + speed * duty * duration * swing)
            height.append(0.05 * math.sin(math.pi * swing))
    assert stride_from_contact(forward, height, duration) == pytest.approx(speed * duration, rel=0.02)
    with pytest.raises(ValueError):
        stride_from_contact([0.0] * 10, [0.0] * 10, duration)


def minimal_glb(weights, joints=None):
    """A tiny GLB holding one skinned triangle's JOINTS_0/WEIGHTS_0 accessors."""
    joints = joints or [(0, 1, 0, 0)] * len(weights)
    weight_bytes = b''.join(struct.pack('<4f', *w) for w in weights)
    joint_bytes = b''.join(struct.pack('<4B', *j) for j in joints)
    position_bytes = b''.join(struct.pack('<3f', float(i), 0.0, 0.0) for i in range(len(weights)))
    blob = position_bytes + joint_bytes + weight_bytes
    views = [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(position_bytes)},
             {'buffer': 0, 'byteOffset': len(position_bytes), 'byteLength': len(joint_bytes)},
             {'buffer': 0, 'byteOffset': len(position_bytes) + len(joint_bytes), 'byteLength': len(weight_bytes)}]
    doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(blob)}], 'bufferViews': views,
           'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': len(weights), 'type': 'VEC3'},
                         {'bufferView': 1, 'componentType': 5121, 'count': len(weights), 'type': 'VEC4'},
                         {'bufferView': 2, 'componentType': 5126, 'count': len(weights), 'type': 'VEC4'}],
           'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'JOINTS_0': 1, 'WEIGHTS_0': 2}}]}],
           'skins': [{'joints': [0, 1]}], 'nodes': [{}, {}]}
    text = json.dumps(doc).encode()
    text += b' ' * (-len(text) % 4)
    blob += b'\0' * (-len(blob) % 4)
    body = struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(blob), 0x004E4942) + blob
    return struct.pack('<III', 0x46546C67, 2, 12 + len(body)) + body


def test_glb_skin_report_accepts_normalized_and_flags_bad_weights(tmp_path):
    good = tmp_path / 'good.glb'
    good.write_bytes(minimal_glb([(1, 0, 0, 0), (.5, .5, 0, 0), (.25, .25, .25, .25)]))
    report = glb_skin_report(good)
    assert report['vertices'] == 3 and report['max_weight_sum_error'] < 1e-6
    assert report['unbound_vertices'] == 0 and report['negative_or_nonfinite'] == 0
    bad = tmp_path / 'bad.glb'
    bad.write_bytes(minimal_glb([(0, 0, 0, 0), (.7, .7, 0, 0), (float('nan'), 0, 0, 0)]))
    report = glb_skin_report(bad)
    assert report['unbound_vertices'] == 1 and report['negative_or_nonfinite'] == 1
    assert report['max_weight_sum_error'] > .3
    with pytest.raises(ValueError):
        (tmp_path / 'not.glb').write_bytes(b'nope')
        glb_skin_report(tmp_path / 'not.glb')


def test_planted_paw_path_moves_backward_at_body_speed_and_lifts_only_in_swing():
    n, stride, lift = 20, 0.8, 0.1
    heights = [0.0] * 12 + [0.05, 0.1, 0.15, 0.2, 0.15, 0.1, 0.05, 0.02]
    heights = heights[5:] + heights[:5]                          # stance wraps around the cycle start
    path = planted_paw_path(heights, stride, lift)
    planted = [i for i, h in enumerate(heights) if h <= 0.03]
    for a, b in zip(planted, planted[1:]):
        if b == a + 1:
            assert path[b][0] - path[a][0] == pytest.approx(-stride / n)
    assert all(path[i][1] == 0 for i in planted)
    assert max(h for _, h in path) == pytest.approx(lift, rel=0.05)
    offsets = [f for f, _ in path]
    assert max(offsets) == pytest.approx(-min(offsets))          # sweep centred on the rest paw
    with pytest.raises(ValueError):
        planted_paw_path([0.0] * n, stride, lift)
