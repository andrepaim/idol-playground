"""Authored numeric fixtures; no imported meshes, native libraries or inference."""
import copy
import json
import math

import pytest

from mesh_diagnostics import MeshTransform, diagnose_mesh


TRIANGLE = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]
IDENTITY = ((1., 0., 0., 0.), (0., 1., 0., 0.), (0., 0., 1., 0.), (0., 0., 0., 1.))


def test_valid_triangle_report_is_json_safe_immutable_and_non_destructive():
    vertices, faces = copy.deepcopy(TRIANGLE), [[0, 1, 2]]
    before = copy.deepcopy((vertices, faces))
    report = diagnose_mesh(vertices, faces)
    assert report.geometry_valid
    assert report.within_runtime_budget
    assert report.target_met
    assert report.bounds == ((0., 0., 0.), (1., 1., 0.))
    assert report.diagonal == math.sqrt(2)
    assert report.component_triangle_counts == (1,)
    assert report.roundtrip_error == 0
    assert report.transform.identity_assumed
    assert report.unreferenced_vertices == 0
    assert (vertices, faces) == before
    assert json.loads(json.dumps(report.as_dict(), allow_nan=False))['schema'] == 'mesh-diagnostics-v1'
    with pytest.raises(AttributeError):
        report.geometry_valid = False


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf'), True, '1'])
def test_invalid_positions_do_not_receive_partial_bounds_or_validity(bad):
    report = diagnose_mesh(TRIANGLE + [[bad, 0, 0]], [[0, 1, 2]])
    assert not report.geometry_valid
    assert report.invalid_positions.count == 1
    assert report.invalid_positions.examples == (3,)
    assert report.bounds is None and report.diagonal is None
    assert report.roundtrip_error is None
    json.dumps(report.as_dict(), allow_nan=False)


@pytest.mark.parametrize('row', [None, [0, 0], [0, 0, 0, 0], 42])
def test_malformed_position_rows_are_diagnosed(row):
    assert diagnose_mesh([row], []).invalid_positions.count == 1


@pytest.mark.parametrize('face', [[0, 1, 3], [-1, 1, 2], [False, 1, 2], [0., 1, 2], [0, 1], None])
def test_invalid_indices_and_face_shapes_are_reported_without_indexing(face):
    report = diagnose_mesh(TRIANGLE, [face])
    assert not report.geometry_valid
    assert report.invalid_triangles.count == 1
    assert report.component_triangle_counts == ()


def test_faces_using_nonfinite_vertices_are_invalid():
    report = diagnose_mesh([[0, 0, 0], [1, 0, 0], [0, math.nan, 0]], [[0, 1, 2]])
    assert report.invalid_triangles.count == 1
    assert not report.geometry_valid


def test_repeated_and_collinear_triangles_are_not_usable_components():
    report = diagnose_mesh(TRIANGLE + [[2, 0, 0]], [[0, 1, 2], [0, 0, 1], [0, 1, 3]])
    assert report.degenerate_triangles.count == 2
    assert report.degenerate_triangles.examples == (1, 2)
    assert report.component_triangle_counts == (1,)
    assert not report.geometry_valid


def test_edge_connected_components_do_not_weld_coincident_or_point_contacts():
    # First two share an edge; third touches at vertex0; last uses duplicate positions at new indices.
    points = TRIANGLE + [[1, 1, 0], [-1, 0, 0], [0, -1, 0]] + copy.deepcopy(TRIANGLE) + [[99, 99, 99]]
    faces = [[0, 1, 2], [1, 3, 2], [0, 4, 5], [6, 7, 8]]
    report = diagnose_mesh(points, faces)
    assert report.component_triangle_counts == (2, 1, 1)
    assert report.unreferenced_vertices == 1
    assert report.geometry_valid  # Detached accessories require review, not automatic removal/rejection.
    assert 'disconnected_components' in report.review_reasons
    assert 'unreferenced_vertices' in report.review_reasons
    assert faces[-1] == [6, 7, 8]


def test_empty_and_zero_extent_meshes_are_blocked():
    empty = diagnose_mesh([], [])
    assert not empty.geometry_valid and empty.bounds is None
    flat = diagnose_mesh([[1, 1, 1]] * 3, [[0, 1, 2]])
    assert flat.diagonal == 0
    assert 'invalid_bounds' in flat.blocking_reasons
    assert flat.degenerate_triangles.count == 1


@pytest.mark.parametrize('count,target_ok,max_ok', [(50_000, True, True), (50_001, False, True),
                                                   (100_000, False, True), (100_001, False, False)])
def test_adopted_triangle_budget_boundaries_count_all_source_faces(count, target_ok, max_ok):
    # Repeated faces intentionally isolate count boundaries; manifold/duplicates are outside this module.
    report = diagnose_mesh(TRIANGLE, [[0, 1, 2]] * count)
    assert report.triangles == count
    assert report.target_met is target_ok
    assert report.within_runtime_budget is max_ok
    assert report.geometry_valid
    assert report.triangle_target == 50_000 and report.triangle_maximum == 100_000


def test_invalid_faces_cannot_be_dropped_to_evade_budget():
    report = diagnose_mesh(TRIANGLE, [[0, 1, 99]] * 100_001)
    assert not report.within_runtime_budget
    assert report.invalid_triangles.count == 100_001
    assert report.invalid_triangles.examples == tuple(range(20))


def test_explicit_transform_preserves_source_and_validates_inverse():
    # x'=-2y+10, y'=3x-4, z'=4z+8: rotation, nonuniform scale and translation.
    forward = ((0, -2, 0, 10), (3, 0, 0, -4), (0, 0, 4, 8), (0, 0, 0, 1))
    inverse = ((0, 1/3, 0, 4/3), (-.5, 0, 0, 5), (0, 0, .25, -2), (0, 0, 0, 1))
    transform = MeshTransform(forward, inverse, source_axes='Z-up right-handed', source_units='centimetres',
                              origin='explicit user reference')
    report = diagnose_mesh(TRIANGLE, [[0, 1, 2]], transform=transform)
    assert report.geometry_valid
    assert report.bounds == ((8., -4., 8.), (10., -1., 8.))
    assert report.diagonal == math.sqrt(13)
    assert report.roundtrip_error <= 1e-5 * report.diagonal
    assert not report.transform.identity_assumed
    assert report.transform.source_units == 'centimetres'
    assert report.transform.canonical_units == 'metres'
    assert TRIANGLE == [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]


def test_wrong_inverse_is_blocked_even_for_points_where_roundtrip_happens_to_match():
    # Source sits entirely on z=0, so checking observed points alone would miss z inverse error.
    bad_inverse = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 2, 0), (0, 0, 0, 1))
    report = diagnose_mesh(TRIANGLE, [[0, 1, 2]], transform=MeshTransform(IDENTITY, bad_inverse))
    assert not report.geometry_valid
    assert 'inconsistent_inverse' in report.blocking_reasons


def test_reflection_requires_winding_review_without_silent_repair():
    reflection = ((-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    report = diagnose_mesh(TRIANGLE, [[0, 1, 2]], transform=MeshTransform(reflection, reflection))
    assert report.geometry_valid
    assert report.transform_reflects
    assert 'reflected_winding' in report.review_reasons


@pytest.mark.parametrize('matrix', [((1, 0),), ((1, 0, 0, math.inf),) * 4,
    ((1, 0, 0, 0), (0, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)),
    ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, .1, 1))])
def test_invalid_projective_or_singular_transform_rejected(matrix):
    with pytest.raises(ValueError):
        MeshTransform(matrix, IDENTITY)


def test_coordinate_metadata_and_transform_snapshot_cannot_change_after_creation():
    mutable = [list(row) for row in IDENTITY]
    transform = MeshTransform(mutable, mutable)
    mutable[0][0] = 7
    assert transform.source_to_canonical == IDENTITY
    with pytest.raises(ValueError):
        MeshTransform(source_units='')


def test_scale_normalized_area_tolerance_is_explicit_and_scale_independent():
    thin = [[0, 0, 0], [1, 0, 0], [1, 1e-8, 0]]
    for scale in (1e-12, 1, 1e12):
        points = [[value * scale for value in point] for point in thin]
        assert diagnose_mesh(points, [[0, 1, 2]]).geometry_valid
        report = diagnose_mesh(points, [[0, 1, 2]], minimum_relative_area=1e-7)
        assert not report.geometry_valid
        assert report.minimum_relative_area == 1e-7
        assert report.degenerate_triangles.count == 1


def test_nonfinite_derived_geometry_never_serializes_nan_or_receives_validity():
    huge = [[-1e308, 0, 0], [1e308, 0, 0], [0, 1e308, 0]]
    report = diagnose_mesh(huge, [[0, 1, 2]])
    assert not report.geometry_valid
    assert report.diagonal is None
    assert 'invalid_bounds' in report.blocking_reasons
    json.dumps(report.as_dict(), allow_nan=False)


def test_normals_are_optional_but_supplied_invalid_normals_block_geometry():
    assert diagnose_mesh(TRIANGLE, [[0, 1, 2]]).normals_checked is False
    report = diagnose_mesh(TRIANGLE, [[0, 1, 2]], normals=[[0, 0, 1]] * 3)
    assert report.geometry_valid and report.normals_checked
    report = diagnose_mesh(TRIANGLE, [[0, 1, 2]], normals=[[0, 0, 1], [math.inf, 0, 1], [0, 1]])
    assert report.invalid_normals.count == 2
    assert not report.geometry_valid
    assert 'invalid_normals' in report.blocking_reasons
    assert not diagnose_mesh(TRIANGLE, [[0, 1, 2]], normals=[]).geometry_valid


@pytest.mark.parametrize('settings', [{'minimum_relative_area': math.nan}, {'minimum_relative_area': -1},
                                     {'triangle_target': 0}, {'triangle_maximum': True},
                                     {'triangle_target': 100, 'triangle_maximum': 99}])
def test_invalid_thresholds_are_rejected(settings):
    with pytest.raises(ValueError):
        diagnose_mesh(TRIANGLE, [[0, 1, 2]], **settings)


def test_small_mesh_still_checks_observed_roundtrip_below_matrix_consistency_tolerance():
    points = [[0, 0, 0], [1e-12, 0, 0], [0, 1e-12, 0]]
    near_inverse = ((1, 0, 0, 1e-10), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    report = diagnose_mesh(points, [[0, 1, 2]], transform=MeshTransform(IDENTITY, near_inverse))
    assert 'inconsistent_inverse' not in report.blocking_reasons
    assert 'transform_roundtrip' in report.blocking_reasons
    assert report.roundtrip_error > report.roundtrip_limit


def test_overflowing_transform_is_an_invalid_position_not_a_crash_or_nan():
    forward = ((2, 0, 0, 0), (0, 2, 0, 0), (0, 0, 2, 0), (0, 0, 0, 1))
    inverse = ((.5, 0, 0, 0), (0, .5, 0, 0), (0, 0, .5, 0), (0, 0, 0, 1))
    report = diagnose_mesh([[1e308, 0, 0], [0, 1, 0], [0, 0, 1]], [[0, 1, 2]],
                           transform=MeshTransform(forward, inverse))
    assert report.invalid_positions.examples == (0,)
    assert report.invalid_triangles.count == 1
    assert not report.geometry_valid
    json.dumps(report.as_dict(), allow_nan=False)


def test_roundtrip_metric_uses_canonical_units_instead_of_source_units():
    # Inverse offset1e-10 source units is only1e-12 canonical metres.
    forward = ((.01, 0, 0, 0), (0, .01, 0, 0), (0, 0, .01, 0), (0, 0, 0, 1))
    inverse = ((100, 0, 0, 1e-10), (0, 100, 0, 0), (0, 0, 100, 0), (0, 0, 0, 1))
    report = diagnose_mesh(TRIANGLE, [[0, 1, 2]],
                           transform=MeshTransform(forward, inverse, source_units='centimetres'))
    assert report.geometry_valid
    assert report.roundtrip_error == pytest.approx(1e-12)


def test_large_translation_does_not_turn_a_collinear_triangle_into_nonzero_area():
    # Absolute-coordinate normalization rounds away different low bits of each vertex.
    points = [[1e16, 1e16, 0], [1e16+2, 1e16+4, 0], [1e16+4, 1e16+8, 0]]
    report = diagnose_mesh(points, [[0, 1, 2]])
    assert not report.geometry_valid
    assert report.degenerate_triangles.count == 1
