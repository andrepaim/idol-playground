"""Pure-Python geometry helpers for the template-skeleton vertical slice (issue #72).

Canonical frame, matching the Fox reference rig: +Z up, head toward -Y, left side +X, floor z=0.
No numpy, so the helpers run in CI, in Blender's bundled Python and in any repository environment.
These are experiment heuristics for one feasibility case, not a product rigging contract.
"""
import heapq
import json
import math
import struct
from collections import defaultdict


class AnatomyError(ValueError):
    """The mesh lacks anatomy the quadruped template needs (e.g. four separable paws)."""


def _points(points, minimum=4):
    rows = [tuple(float(v) for v in p) for p in points]
    if len(rows) < minimum or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in rows):
        raise ValueError(f'need at least {minimum} finite 3D points')
    return rows


def apply_matrix(matrix, point):
    x, y, z = point
    return tuple(r[0] * x + r[1] * y + r[2] * z + r[3] for r in matrix[:3])


def _yaw_matrix(angle, offset=(0.0, 0.0, 0.0)):
    c, s = math.cos(angle), math.sin(angle)
    return [[c, -s, 0.0, offset[0]], [s, c, 0.0, offset[1]], [0.0, 0.0, 1.0, offset[2]], [0.0, 0.0, 0.0, 1.0]]


def canonicalize(points):
    """Proper yaw rotation + translation into the canonical frame. Z is assumed to already be up.

    The body's long horizontal axis comes from 2D PCA. The head end is the end with more surface in
    the upper half of the body (head and neck outweigh a tail). Returns (row-major 4x4, report).
    """
    rows = _points(points)
    n = len(rows)
    mx = sum(p[0] for p in rows) / n
    my = sum(p[1] for p in rows) / n
    sxx = sum((p[0] - mx) ** 2 for p in rows) / n
    syy = sum((p[1] - my) ** 2 for p in rows) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in rows) / n
    if sxx + syy <= 0:
        raise ValueError('points have no horizontal extent')
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)             # principal axis angle from +X
    yaw = math.pi / 2 - theta                                 # rotate the principal axis onto +Y
    rotated = [apply_matrix(_yaw_matrix(yaw), p) for p in rows]
    ys = [p[1] for p in rotated]
    zs = [p[2] for p in rotated]
    y0, y1, z0, z1 = min(ys), max(ys), min(zs), max(zs)
    if y1 - y0 <= 0 or z1 - z0 <= 0:
        raise ValueError('points have degenerate bounds')
    end = 0.25 * (y1 - y0)
    upper = z0 + 0.5 * (z1 - z0)
    low_end = sum(1 for p in rotated if p[2] > upper and p[1] < y0 + end)
    high_end = sum(1 for p in rotated if p[2] > upper and p[1] > y1 - end)
    if high_end > low_end:                                    # head currently toward +Y: turn around
        yaw += math.pi
        rotated = [(-p[0], -p[1], p[2]) for p in rotated]
    xs = [p[0] for p in rotated]
    ys = [p[1] for p in rotated]
    offset = (-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -z0)
    matrix = _yaw_matrix(yaw, offset)
    report = {'yaw_radians': math.remainder(yaw, 2 * math.tau), 'length': max(ys) - min(ys),
              'width': max(xs) - min(xs), 'height': z1 - z0,
              'head_votes': max(low_end, high_end), 'tail_votes': min(low_end, high_end)}
    return matrix, report


def _band_samples(rows, triangles, limit, spacing):
    """Vertices plus barycentric samples of triangles reaching below `limit`, so sparse low-poly
    paws still form contiguous blobs at the grid resolution."""
    samples = [p for p in rows if p[2] <= limit]
    for tri in triangles or ():
        a, b, c = (rows[int(i)] for i in tri)
        if min(a[2], b[2], c[2]) > limit:
            continue
        n = max(1, math.ceil(max(math.dist(a, b), math.dist(b, c), math.dist(a, c)) / spacing))
        for i in range(n + 1):
            for j in range(n + 1 - i):
                u, v = i / n, j / n
                p = tuple(a[k] + u * (b[k] - a[k]) + v * (c[k] - a[k]) for k in range(3))
                if p[2] <= limit:
                    samples.append(p)
    return samples


def foot_clusters(points, triangles=None, band=0.04, cell=0.0125, minimum_share=0.05):
    """Find four paws as connected floor-contact blobs in canonical coordinates.

    Pass triangles unless vertices are much denser than the grid (cell x body length): the floor band
    is then sampled across faces. The fine default cell separates closely placed fore paws.
    Raises AnatomyError unless exactly four blobs form a fore pair (toward -Y) and a hind pair.
    """
    rows = _points(points)
    z0 = min(p[2] for p in rows)
    height = max(p[2] for p in rows) - z0
    xs = [p[0] for p in rows]
    ys = [p[1] for p in rows]
    size = cell * max(max(xs) - min(xs), max(ys) - min(ys))
    low = _band_samples(rows, triangles, z0 + band * height, size / 2)
    grid = defaultdict(list)
    for p in low:
        grid[(math.floor(p[0] / size), math.floor(p[1] / size))].append(p)
    seen, blobs = set(), []
    for start in grid:
        if start in seen:
            continue
        seen.add(start)
        stack, members = [start], []
        while stack:
            key = stack.pop()
            members += grid[key]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nxt = (key[0] + dx, key[1] + dy)
                    if nxt in grid and nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
        blobs.append(members)
    blobs = [b for b in blobs if len(b) >= minimum_share * len(low)]
    if len(blobs) != 4:
        raise AnatomyError(f'expected 4 separate paws on the floor, found {len(blobs)} contact blobs')

    def summary(members):
        k = len(members)
        center = tuple(sum(p[i] for p in members) / k for i in range(3))
        return {'center': center, 'count': k, 'min_y': min(p[1] for p in members),
                'max_y': max(p[1] for p in members), 'toe': (center[0], min(p[1] for p in members), center[2])}

    paws = sorted((summary(b) for b in blobs), key=lambda s: s['center'][1])
    fore, hind = paws[:2], paws[2:]
    if max(p['center'][1] for p in fore) >= min(p['center'][1] for p in hind) - size:
        raise AnatomyError('paws do not form separate fore and hind pairs')
    fore.sort(key=lambda s: -s['center'][0])                  # +X is the animal's left
    hind.sort(key=lambda s: -s['center'][0])
    return {'fore_left': fore[0], 'fore_right': fore[1], 'hind_left': hind[0], 'hind_right': hind[1]}


def landmarks(points, triangles=None, bins=50):
    """Canonical-frame landmarks shared by template and target fitting."""
    rows = _points(points)
    feet = foot_clusters(rows, triangles)
    ys = [p[1] for p in rows]
    y0, y1 = min(ys), max(ys)
    width = (y1 - y0) / bins
    tops = [None] * bins
    for p in rows:
        i = min(bins - 1, int((p[1] - y0) / width))
        if tops[i] is None or p[2] > tops[i]:
            tops[i] = p[2]
    profile = [(y0 + (i + .5) * width, t) for i, t in enumerate(tops) if t is not None]
    return {'feet': feet, 'nose_y': y0, 'rear_y': y1, 'length': y1 - y0,
            'height': max(p[2] for p in rows) - min(p[2] for p in rows),
            'fore_y': (feet['fore_left']['center'][1] + feet['fore_right']['center'][1]) / 2,
            'hind_y': (feet['hind_left']['center'][1] + feet['hind_right']['center'][1]) / 2,
            'top_profile': profile}


def top_at(marks, y):
    """Highest surface point near y (linear interpolation of the binned back/head line)."""
    profile = marks['top_profile']
    if y <= profile[0][0]:
        return profile[0][1]
    for (ya, za), (yb, zb) in zip(profile, profile[1:]):
        if ya <= y <= yb:
            return za + (zb - za) * (y - ya) / (yb - ya)
    return profile[-1][1]


def _max_angular_gap(center, rows):
    angles = sorted(math.atan2(p[1] - center[1], p[0] - center[0]) for p in rows)
    if len(angles) < 3:
        return math.tau
    gaps = [b - a for a, b in zip(angles, angles[1:])] + [angles[0] + math.tau - angles[-1]]
    return max(gaps)


def limb_centerline(points, foot, top, step, radius, open_degrees=60):
    """Track a leg upward from a paw by horizontal slices.

    Each slice's centroid follows the limb while the slice is a closed ring around it. Two consecutive
    open (or empty) slices mean the trace has reached the torso; the position then freezes at the
    last closed ring, so torso surface never drags upper joints sideways.
    """
    rows = _points(points)
    if step <= 0 or radius <= 0:
        raise ValueError('step and radius must be positive')
    cx, cy = foot[0], foot[1]
    good, suspicious, frozen = (cx, cy), False, False
    z, line = foot[2], []
    while z <= top + 1e-9:
        if not frozen:
            ring = [p for p in rows if abs(p[2] - z) <= step / 2 and math.hypot(p[0] - cx, p[1] - cy) <= radius]
            opened = not ring or _max_angular_gap((cx, cy), ring) > math.radians(open_degrees)
            if opened and suspicious:
                frozen = True
                line[-1] = (good[0], good[1], line[-1][2])
                cx, cy = good
            else:
                if ring:
                    cx = sum(p[0] for p in ring) / len(ring)
                    cy = sum(p[1] for p in ring) / len(ring)
                suspicious = opened
                if not opened:
                    good = (cx, cy)
        line.append((cx, cy, z))
        z += step
    if not line or line[-1][2] < top - 1e-9:
        line.append((cx, cy, top))
    return line


def centerline_at(line, z):
    if z <= line[0][2]:
        return line[0]
    for a, b in zip(line, line[1:]):
        if a[2] <= z <= b[2]:
            t = 0 if b[2] == a[2] else (z - a[2]) / (b[2] - a[2])
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), z)
    return (line[-1][0], line[-1][1], z)


def geodesic(points, triangles, sources):
    """Dijkstra edge-path distances over the triangle graph from the given vertex indices."""
    adjacency = defaultdict(set)
    for tri in triangles:
        a, b, c = (int(i) for i in tri)
        adjacency[a] |= {b, c}
        adjacency[b] |= {a, c}
        adjacency[c] |= {a, b}
    dist = [math.inf] * len(points)
    heap = []
    for s in sources:
        dist[s] = 0.0
        heap.append((0.0, s))
    heapq.heapify(heap)
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist[v]:
            continue
        pv = points[v]
        for w in adjacency[v]:
            nd = d + math.dist(pv, points[w])
            if nd < dist[w]:
                dist[w] = nd
                heapq.heappush(heap, (nd, w))
    return dist


def tail_centerline(points, triangles, marks, step_fraction=0.01, growth=1.6, min_fraction=0.1):
    """Base-to-tip tail centerline from geodesic rings, or None when no slender tail exists.

    The tip is the rear-half vertex, nearer the back than any paw, farthest (along the surface) from the middle of the
    back. Past the rounded tip, rings of equal geodesic distance keep a near-constant radius along a
    tail and grow steadily at a body corner, so a plateau lasting several radii marks a tail.
    """
    rows = _points(points)
    mid_y = (marks['fore_y'] + marks['hind_y']) / 2
    seed_target = (0.0, mid_y, marks['height'])
    seed = min(range(len(rows)), key=lambda i: math.dist(rows[i], seed_target))
    from_back = geodesic(rows, triangles, [seed])
    # Leg surface is closer (along the surface) to a paw than to the back; a tail, raised or hanging,
    # is reached from the paws only by climbing through the body, so it stays a candidate.
    floor = min(p[2] for p in rows) + 0.04 * marks['height']
    from_paws = geodesic(rows, triangles, [i for i, p in enumerate(rows) if p[2] <= floor])
    candidates = [i for i, p in enumerate(rows)
                  if p[1] > mid_y and math.isfinite(from_back[i]) and from_paws[i] > from_back[i]]
    if not candidates:
        return None
    tip = max(candidates, key=lambda i: from_back[i])
    from_tip = geodesic(rows, triangles, [tip])
    edges = sorted(math.dist(rows[int(t[0])], rows[int(t[1])]) for t in triangles)
    step = max(step_fraction * marks['length'], edges[len(edges) // 2])
    rings, k, cap = [], 1, None
    while k * step < marks['length']:
        d = k * step
        ring = [rows[i] for i, v in enumerate(from_tip) if abs(v - d) <= step / 2]
        if len(ring) < 3:
            break
        centroid = tuple(sum(p[i] for p in ring) / len(ring) for i in range(3))
        radius = sum(math.dist(p, centroid) for p in ring) / len(ring)
        rings.append((d, centroid, radius))
        if cap is None and d > 1.5 * radius:
            cap = len(rings) - 1                          # past the rounded tip
        if cap is not None and len(rings) - cap > 3:
            usual = sorted(r for _, _, r in rings[cap:-1])[(len(rings) - 1 - cap) // 2]
            if radius > growth * usual:
                break
        k += 1
    if cap is None or len(rings) - cap < 4:
        return None
    base_index = len(rings) - 2
    length, base_radius = rings[base_index][0], rings[base_index][2]
    if length < min_fraction * marks['length'] or length < 3 * base_radius:
        return None
    return [c for _, c, _ in reversed(rings[:base_index + 1])] + [rows[tip]]


def _interp(anchors, value):
    """Piecewise-linear map through sorted (source, target) anchors, extrapolating end segments."""
    if value <= anchors[1][0]:
        (a, b), (c, d) = anchors[0], anchors[1]
    elif value >= anchors[-2][0]:
        (a, b), (c, d) = anchors[-2], anchors[-1]
    else:
        for (a, b), (c, d) in zip(anchors, anchors[1:]):
            if a <= value <= c:
                break
    return b + (d - b) * (value - a) / (c - a)


def _resample(line, count):
    """`count` points at equal arc-length fractions from line[0] (fraction 0) to line[-1] (fraction 1)."""
    lengths = [0.0]
    for a, b in zip(line, line[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    total = lengths[-1] or 1.0
    out = []
    for i in range(count):
        target = total * i / max(1, count - 1)
        for j in range(1, len(line)):
            if lengths[j] >= target:
                t = 0 if lengths[j] == lengths[j - 1] else (target - lengths[j - 1]) / (lengths[j] - lengths[j - 1])
                out.append(tuple(line[j - 1][k] + t * (line[j][k] - line[j - 1][k]) for k in range(3)))
                break
        else:
            out.append(line[-1])
    return out


def surface_samples(points, triangles, spacing):
    """Vertices plus barycentric samples of every triangle at about `spacing`, for sparse meshes."""
    rows = _points(points)
    return _band_samples(rows, triangles, math.inf, spacing)


def midline_section(points, y, length, width, slab=0.015, band=0.15):
    """(bottom, top) of the body's midline cross-section near y, or None if the slab is empty."""
    zs = [p[2] for p in points if abs(p[1] - y) <= slab * length and abs(p[0]) <= band * width]
    return (min(zs), max(zs)) if zs else None


def back_height(marks):
    """Median back-line height between the fore and hind paws (excludes head and tail extremes)."""
    zs = sorted(z for y, z in marks['top_profile'] if marks['fore_y'] <= y <= marks['hind_y'])
    if not zs:
        raise AnatomyError('no back line between fore and hind paws')
    return zs[len(zs) // 2]


def fit_quadruped(template, template_marks, target_points, target_triangles, target_marks, spec,
                  template_points=None, paw_lift=0.15):
    """Move named template joint heads onto a target quadruped mesh (both canonical).

    Spine/neck/head joints and each leg's top joint keep their relative height within the body's
    midline cross-section; lower leg joints are interpolated between that and the paw, and follow the
    target's own limb centerlines horizontally. The tail follows the target's geodesic tail centerline, or is collapsed and reported
    when no tail is found. `template_points` (canonical template mesh) enables section mapping.
    """
    rows = _points(target_points)
    anchors = sorted([(template_marks['nose_y'], target_marks['nose_y']),
                      (template_marks['fore_y'], target_marks['fore_y']),
                      (template_marks['hind_y'], target_marks['hind_y'])])
    scale = ((target_marks['hind_y'] - target_marks['nose_y'])
             / (template_marks['hind_y'] - template_marks['nose_y']))
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError('template and target landmarks give an invalid body scale')
    k = back_height(target_marks) / back_height(template_marks)
    t_rows = _points(template_points) if template_points is not None else None
    t_width = max(p[0] for p in t_rows) - min(p[0] for p in t_rows) if t_rows else None
    width = max(p[0] for p in rows) - min(p[0] for p in rows)
    warnings, centerlines, joints = [], {}, {}

    def midline(point):
        y = _interp(anchors, point[1])
        if point[2] <= 0:
            return (0.0, y, 0.0)
        source = midline_section(t_rows, point[1], template_marks['length'], t_width) if t_rows else None
        target = midline_section(rows, y, target_marks['length'], width)
        thick = 0.1 * template_marks['height']
        if source and target and source[1] - source[0] > thick:
            fraction = (point[2] - source[0]) / (source[1] - source[0])
            return (0.0, y, target[0] + fraction * (target[1] - target[0]))
        return (0.0, y, point[2] * k)

    for name in spec['spine']:
        joints[name] = midline(template[name])

    height = target_marks['height']
    for leg, chain in spec['legs'].items():
        foot = target_marks['feet'][leg]['center']
        pair = 'fore' if leg.startswith('fore') else 'hind'
        spacing = math.dist(target_marks['feet'][f'{pair}_left']['center'][:2],
                            target_marks['feet'][f'{pair}_right']['center'][:2])
        t_top, t_paw = template[chain[0]][2], template[chain[-1]][2]
        top = midline(template[chain[0]])[2]               # same section mapping as the spine
        # Keep the paw joint above the sole (>= paw_lift x leg height) so the paw bone, not the
        # rotating limb segment above it, owns the whole sole when skinned.
        paw = max(foot[2], t_paw * k, paw_lift * top)
        line = limb_centerline(rows, foot, top, step=0.02 * height, radius=0.45 * spacing)
        centerlines[leg] = line
        for name in chain:
            u = 0.0 if t_top == t_paw else (template[name][2] - t_paw) / (t_top - t_paw)
            joints[name] = centerline_at(line, paw + u * (top - paw))

    # Shoulder/hip sockets mirror each other even when the standing legs (and their traces) do not.
    for pair in ('fore', 'hind'):
        left, right = spec['legs'].get(f'{pair}_left'), spec['legs'].get(f'{pair}_right')
        if left and right:
            a, b = joints[left[0]], joints[right[0]]
            x, y, z = (abs(a[0]) + abs(b[0])) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2
            joints[left[0]], joints[right[0]] = (x, y, z), (-x, y, z)

    tail_names = spec.get('tail', [])
    tail = tail_centerline(rows, target_triangles, target_marks) if tail_names else None
    tail_tip = None
    if tail_names and tail:
        for name, point in zip(tail_names, _resample(tail, len(tail_names) + 1)):
            joints[name] = point
        tail_tip = tail[-1]
    elif tail_names:
        base = midline(template[tail_names[0]])
        for name in tail_names:
            joints[name] = base
        warnings.append('tail not found: tail chain collapsed at the rump and should not deform')
    return {'joints': joints, 'tail_found': bool(tail), 'tail_tip': tail_tip, 'warnings': warnings,
            'leg_centerlines': centerlines, 'scale': scale, 'height_ratio': k}


def stride_from_contact(forward, height, duration, stance_fraction=0.15):
    """Body travel per in-place cycle from one paw's planted backward sweep.

    `forward` and `height` sample one cycle uniformly in the body frame. While planted, the paw moves
    backward at body speed, so stride = median planted speed × cycle duration.
    """
    if len(forward) != len(height) or len(forward) < 4 or duration <= 0:
        raise ValueError('need matching samples over a positive cycle duration')
    lo, hi = min(height), max(height)
    if not math.isfinite(hi - lo) or hi - lo <= 1e-9:
        raise ValueError('paw never lifts; stance cannot be identified')
    planted = [h <= lo + stance_fraction * (hi - lo) for h in height]
    dt = duration / len(forward)
    speeds = sorted(-(forward[i + 1] - forward[i]) / dt
                    for i in range(len(forward) - 1) if planted[i] and planted[i + 1])
    if not speeds:
        raise ValueError('no consecutive planted samples')
    speed = speeds[len(speeds) // 2]
    if speed <= 0:
        raise ValueError('planted paw does not move backward; no forward travel implied')
    return speed * duration


def planted_paw_path(heights, stride, lift, stance_fraction=0.15):
    """IK target path for one paw over one in-place cycle sampled uniformly (cyclic, n samples).

    Contact timing comes from `heights` (e.g. the retargeted source clip). While planted the paw moves
    backward at exactly stride/cycle, centred on its rest position (offset 0); during swing it returns
    with a smoothstep and lifts by a sine arc of height `lift`. Returns [(forward_offset, height), ...].
    """
    n = len(heights)
    if n < 4 or not stride > 0 or not lift >= 0:
        raise ValueError('need at least 4 samples, a positive stride and non-negative lift')
    lo, hi = min(heights), max(heights)
    if hi - lo <= 1e-12:
        raise ValueError('paw never lifts; stance cannot be identified')
    planted = [h <= lo + stance_fraction * (hi - lo) for h in heights]
    if all(planted):
        raise ValueError('paw never leaves the ground')
    first_swing = planted.index(False)
    best = (0, 0)                                          # (length, start) of the longest cyclic run
    run_start, run = None, 0
    for step in range(2 * n):
        i = (first_swing + step) % n
        if planted[i]:
            if run == 0:
                run_start = i
            run += 1
            if run > best[0] and run <= n:
                best = (run, run_start)
        else:
            run = 0
    length, start = best
    if length < 2:
        raise ValueError('no stance interval')
    per_sample = stride / n
    sweep = per_sample * (length - 1)
    path = [None] * n
    for j in range(length):
        path[(start + j) % n] = (sweep / 2 - per_sample * j, 0.0)
    swing = n - length
    for i in range(1, swing + 1):
        u = i / (swing + 1)
        eased = u * u * (3 - 2 * u)
        path[(start + length - 1 + i) % n] = (-sweep / 2 + sweep * eased, lift * math.sin(math.pi * u))
    return path


_COMPONENTS = {5120: ('b', 1, 127), 5121: ('B', 1, 255), 5122: ('h', 2, 32767), 5123: ('H', 2, 65535),
               5125: ('I', 4, None), 5126: ('f', 4, None)}
_WIDTH = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def _read_glb(path):
    data = open(path, 'rb').read()
    if len(data) < 20 or data[:4] != b'glTF':
        raise ValueError('not a binary glTF file')
    length = struct.unpack_from('<I', data, 12)[0]
    doc = json.loads(data[20:20 + length])
    blob = b''
    offset = 20 + length
    if offset + 8 <= len(data):
        size = struct.unpack_from('<I', data, offset)[0]
        blob = data[offset + 8: offset + 8 + size]
    return doc, blob


def _accessor(doc, blob, index):
    acc = doc['accessors'][index]
    view = doc['bufferViews'][acc['bufferView']]
    code, size, norm = _COMPONENTS[acc['componentType']]
    width = _WIDTH[acc['type']]
    stride = view.get('byteStride') or size * width
    base = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    rows = []
    for i in range(acc['count']):
        values = struct.unpack_from(f'<{width}{code}', blob, base + i * stride)
        if acc.get('normalized') and norm:
            values = tuple(v / norm for v in values)
        rows.append(values)
    return rows


def glb_skin_report(path):
    """Independent accessor-level skin check of an exported GLB (does not trust the exporter)."""
    doc, blob = _read_glb(path)
    joint_count = max((len(s['joints']) for s in doc.get('skins', [])), default=0)
    report = {'vertices': 0, 'triangles': 0, 'unbound_vertices': 0, 'negative_or_nonfinite': 0,
              'max_weight_sum_error': 0.0, 'max_influences': 0, 'invalid_joint_indices': 0,
              'weight_sets': 0, 'joints': joint_count, 'animations': [a.get('name') for a in doc.get('animations', [])]}
    for mesh in doc.get('meshes', []):
        for primitive in mesh['primitives']:
            attributes = primitive['attributes']
            count = doc['accessors'][attributes['POSITION']]['count']
            report['vertices'] += count
            if 'indices' in primitive:
                report['triangles'] += doc['accessors'][primitive['indices']]['count'] // 3
            else:
                report['triangles'] += count // 3
            if 'WEIGHTS_0' not in attributes:
                continue
            report['weight_sets'] = max(report['weight_sets'], sum(1 for k in attributes if k.startswith('WEIGHTS_')))
            weights = _accessor(doc, blob, attributes['WEIGHTS_0'])
            joints = _accessor(doc, blob, attributes['JOINTS_0'])
            for w, j in zip(weights, joints):
                if not all(math.isfinite(v) and v >= 0 for v in w):
                    report['negative_or_nonfinite'] += 1
                    continue
                total = sum(w)
                if total == 0:
                    report['unbound_vertices'] += 1
                    continue
                report['max_weight_sum_error'] = max(report['max_weight_sum_error'], abs(total - 1))
                report['max_influences'] = max(report['max_influences'], sum(1 for v in w if v > 0))
                report['invalid_joint_indices'] += sum(1 for v, k in zip(w, j) if v > 0 and k >= joint_count)
    return report
