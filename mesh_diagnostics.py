"""Non-destructive CPU diagnostics for one indexed triangle mesh.

This module does not parse files, repair geometry, infer anatomy or approve a
playable character. Edge connectivity uses indices; it never welds seams.
"""
from dataclasses import asdict, dataclass
import math
from numbers import Integral, Real


IDENTITY = ((1., 0., 0., 0.), (0., 1., 0., 0.), (0., 0., 1., 0.), (0., 0., 0., 1.))
SAMPLE_LIMIT = 20


def _number(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (OverflowError, ValueError):
        return None


def _vector(value):
    try:
        if len(value) != 3:
            return None
        row = tuple(_number(part) for part in value)
        return row if None not in row else None
    except TypeError:
        return None


def _determinant(matrix):
    # Only sign/non-singularity are needed; row normalization avoids overflow.
    rows = []
    for row in matrix[:3]:
        scale = max(abs(part) for part in row[:3])
        if not scale:
            return 0.
        rows.append(tuple(part / scale for part in row[:3]))
    a, b, c = rows
    return (a[0] * (b[1]*c[2] - b[2]*c[1]) - a[1] * (b[0]*c[2] - b[2]*c[0])
            + a[2] * (b[0]*c[1] - b[1]*c[0]))


def _matrix(value):
    try:
        if len(value) != 4 or any(len(row) != 4 for row in value):
            raise ValueError('Transform must be a row-major 4x4 matrix')
        rows = tuple(tuple(_number(part) for part in row) for row in value)
        if any(part is None for row in rows for part in row) or rows[3] != (0., 0., 0., 1.):
            raise ValueError('Transform must be finite and affine')
        if _determinant(rows) == 0:
            raise ValueError('Transform must be nonsingular')
        return rows
    except TypeError as error:
        raise ValueError('Transform must be a row-major 4x4 matrix') from error


@dataclass(frozen=True)
class MeshTransform:
    """Explicit affine pair; matrices include conversion into canonical metres.

    Defaults mean the caller assumes the source is already canonical. Metadata
    documents the caller's convention, rather than determining the matrices.
    """
    source_to_canonical: tuple = IDENTITY
    canonical_to_source: tuple = IDENTITY
    source_axes: str = 'right-handed Y-up'
    source_units: str = 'metres'
    origin: str = 'source origin retained'
    canonical_axes: str = 'right-handed Y-up'
    canonical_units: str = 'metres'

    def __post_init__(self):
        for name in ('source_to_canonical', 'canonical_to_source'):
            object.__setattr__(self, name, _matrix(getattr(self, name)))
        for name in ('source_axes', 'source_units', 'origin', 'canonical_axes', 'canonical_units'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 160:
                raise ValueError('Coordinate metadata must be nonempty bounded text')
        if self.canonical_axes != 'right-handed Y-up' or self.canonical_units != 'metres':
            raise ValueError('Canonical convention is right-handed Y-up metres')

    @property
    def identity_assumed(self):
        return self.source_to_canonical == self.canonical_to_source == IDENTITY


@dataclass(frozen=True)
class Findings:
    count: int
    examples: tuple[int, ...]


class _Findings:
    def __init__(self):
        self.count = 0
        self.examples = []

    def add(self, index):
        self.count += 1
        if len(self.examples) < SAMPLE_LIMIT:
            self.examples.append(index)

    def freeze(self):
        return Findings(self.count, tuple(self.examples))


@dataclass(frozen=True)
class MeshDiagnostics:
    schema: str
    vertices: int
    triangles: int
    invalid_positions: Findings
    invalid_triangles: Findings
    degenerate_triangles: Findings
    invalid_normals: Findings
    normals_checked: bool
    bounds: tuple | None
    diagonal: float | None
    component_triangle_counts: tuple[int, ...]
    unreferenced_vertices: int
    transform: MeshTransform
    transform_reflects: bool
    roundtrip_error: float | None
    roundtrip_limit: float | None
    minimum_relative_area: float
    triangle_target: int
    triangle_maximum: int
    geometry_valid: bool
    target_met: bool
    within_runtime_budget: bool
    blocking_reasons: tuple[str, ...]
    review_reasons: tuple[str, ...]

    def as_dict(self):
        return asdict(self)


def _apply(matrix, point, *, vector=False):
    try:
        result = tuple(math.fsum(row[i] * point[i] for i in range(3)) + (0 if vector else row[3])
                       for row in matrix[:3])
        return result if all(math.isfinite(value) for value in result) else None
    except (OverflowError, ValueError):
        return None


def _inverse_consistent(forward, inverse):
    try:
        return all(abs(math.fsum(left[row][k] * right[k][column] for k in range(4))
                       - (1 if row == column else 0)) <= 1e-9
                   for left, right in ((forward, inverse), (inverse, forward))
                   for row in range(4) for column in range(4))
    except (OverflowError, ValueError):
        return False


def diagnose_mesh(vertices, triangles, *, transform=None, normals=None,
                  minimum_relative_area=0., triangle_target=50_000, triangle_maximum=100_000):
    """Inspect arrays without mutation; return only counts and bounded examples.

    ``minimum_relative_area`` is triangle area / bounding-box diagonal squared,
    defaulting to zero (reject exactly zero area). Components use only valid,
    nondegenerate triangles sharing an indexed edge. All source triangles count
    toward the budget, including invalid ones. Unreferenced counts use every
    structurally valid face, including degenerate faces. Normals, when supplied,
    must have one finite three-vector per vertex; their direction is not certified.
    """
    area_limit = _number(minimum_relative_area)
    if area_limit is None or area_limit < 0:
        raise ValueError('Relative area threshold must be finite and nonnegative')
    if (any(isinstance(value, bool) or not isinstance(value, Integral) or value <= 0
            for value in (triangle_target, triangle_maximum)) or triangle_target > triangle_maximum):
        raise ValueError('Triangle budgets must be positive integers with target <= maximum')
    transform = MeshTransform() if transform is None else transform
    if not isinstance(transform, MeshTransform):
        raise ValueError('Expected an explicit MeshTransform')
    forward, inverse = transform.source_to_canonical, transform.canonical_to_source
    points, faces = tuple(vertices), tuple(triangles)
    invalid_positions, invalid_triangles, degenerate, invalid_normals = (_Findings() for _ in range(4))
    blocking, review = [], []
    sources, canonical = [], []
    for index, point in enumerate(points):
        source = _vector(point)
        converted = _apply(forward, source) if source is not None else None
        if converted is None:
            invalid_positions.add(index)
        sources.append(source)
        canonical.append(converted)
    bounds, diagonal, roundtrip = None, None, None
    if points and not invalid_positions.count:
        low = tuple(min(point[axis] for point in canonical) for axis in range(3))
        high = tuple(max(point[axis] for point in canonical) for axis in range(3))
        bounds = (low, high)
        length = math.hypot(*(high[axis] - low[axis] for axis in range(3)))
        diagonal = length if math.isfinite(length) else None
        roundtrip = 0.
        for source, point in zip(sources, canonical):
            recovered = _apply(inverse, point)
            delta = _apply(forward, tuple(recovered[i] - source[i] for i in range(3)), vector=True) if recovered else None
            error = math.hypot(*delta) if delta else math.inf
            if not math.isfinite(error):
                roundtrip = None
                break
            roundtrip = max(roundtrip, error)
    if not points:
        blocking.append('empty_vertices')
    if not faces:
        blocking.append('empty_triangles')
    if invalid_positions.count:
        blocking.append('invalid_positions')
    if diagonal is None or diagonal <= 0:
        blocking.append('invalid_bounds')
    if not _inverse_consistent(forward, inverse):
        blocking.append('inconsistent_inverse')
    roundtrip_limit = 1e-5 * diagonal if diagonal is not None else None
    roundtrip_failed = roundtrip is None or roundtrip_limit is None or roundtrip > roundtrip_limit
    if points and not invalid_positions.count and roundtrip_failed:
        blocking.append('transform_roundtrip')
    if normals is not None:
        normals = tuple(normals)
        for index in range(max(len(normals), len(points))):
            if index >= len(normals) or index >= len(points) or _vector(normals[index]) is None:
                invalid_normals.add(index)
        if invalid_normals.count:
            blocking.append('invalid_normals')

    parent, sizes, edges, referenced = {}, {}, {}, set()

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def unite(left, right):
        left, right = root(left), root(right)
        if left != right:
            if sizes[left] < sizes[right]:
                left, right = right, left
            parent[right] = left
            sizes[left] += sizes.pop(right)

    for index, face in enumerate(faces):
        try:
            valid = len(face) == 3 and all(not isinstance(value, bool) and isinstance(value, Integral)
                                          and 0 <= value < len(points) and canonical[value] is not None for value in face)
        except TypeError:
            valid = False
        if not valid:
            invalid_triangles.add(index)
            continue
        face = tuple(int(value) for value in face)
        referenced.update(face)
        a, b, c = (canonical[value] for value in face)
        ab, ac = (tuple(point[i] - a[i] for i in range(3)) for point in (b, c))
        edge_scale = max(abs(value) for edge in (ab, ac) for value in edge)
        if not math.isfinite(edge_scale):
            invalid_triangles.add(index)
            continue
        # Subtract before normalization: scaling absolute positions first can
        # turn an exactly collinear translated triangle into a nonzero area.
        # Scaling edges avoids product underflow/overflow for tiny/huge meshes.
        ab, ac = (tuple(value / (edge_scale or 1.) for value in edge) for edge in (ab, ac))
        cross = (ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
        double_area = math.hypot(*cross)
        relative_area = double_area * (edge_scale / diagonal)**2 / 2 if diagonal else None
        if len(set(face)) < 3 or not double_area or (relative_area is not None and relative_area <= area_limit):
            degenerate.add(index)
            continue
        parent[index], sizes[index] = index, 1
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = (min(start, end), max(start, end))
            if edge in edges:
                unite(index, edges[edge])
            else:
                edges[edge] = index
    if invalid_triangles.count:
        blocking.append('invalid_triangles')
    if degenerate.count:
        blocking.append('degenerate_triangles')
    components = tuple(sorted(sizes.values(), reverse=True))
    unreferenced = len(points) - len(referenced)
    if len(components) > 1:
        review.append('disconnected_components')
    if unreferenced:
        review.append('unreferenced_vertices')
    reflected = _determinant(forward) < 0
    if reflected:
        review.append('reflected_winding')
    if transform.identity_assumed:
        review.append('assumed_canonical_coordinates')
    if len(faces) > triangle_target:
        review.append('above_triangle_target')
    return MeshDiagnostics('mesh-diagnostics-v1', len(points), len(faces), invalid_positions.freeze(),
                           invalid_triangles.freeze(), degenerate.freeze(), invalid_normals.freeze(), normals is not None,
                           bounds, diagonal, components, unreferenced, transform, reflected, roundtrip, roundtrip_limit,
                           area_limit, int(triangle_target), int(triangle_maximum), not blocking,
                           len(faces) <= triangle_target, len(faces) <= triangle_maximum,
                           tuple(blocking), tuple(review))
