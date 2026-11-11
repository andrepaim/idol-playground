# CPU mesh diagnostics foundation

`mesh_diagnostics.diagnose_mesh` inspects one in-memory indexed triangle mesh without modifying positions, triangles or normals. It uses only the Python standard library. It is not registered in the application, worker adapters or legacy export validators. Existing source meshes, completed artifacts and model environments are unaffected.

This is an independently testable part of [M4.2](image-to-playable-milestones.md#m4--reconstruction-quality-and-game-mesh-preparation). It does not complete M4 or approve generated anatomy, appearance, simplification, deformation or playability. Corpus and integrated quality acceptance remain required.

## Input and coordinate contract

Pass vertex three-vectors and indexed triangle three-vectors. Indices must be integers, excluding booleans, in range and reference finite vertices. Malformed rows and nonfinite original or transformed positions are reported with counts and up to twenty zero-based example indices. Nothing is removed or reordered. Optional normals must have one finite three-vector per source vertex; the module does not transform, normalize or certify their directions. Omitted normals remain explicitly unchecked.

A `MeshTransform` records row-major 4×4 source-to-canonical and canonical-to-source affine matrices, source axes/units, origin policy and the canonical convention (right-handed Y-up metres). Its matrices are immutable snapshots. Nonfinite, projective and singular matrices are rejected. Conversion, including unit scaling, must be encoded in the matrices; metadata does not calculate a conversion. The default identity pair explicitly reports `assumed_canonical_coordinates` for review. It does not infer floor, orientation or physical scale.

Both matrix products are checked against identity with absolute coefficient tolerance `1e-9`. The observed vertex round-trip displacement is measured in canonical metres and must not exceed `1e-5 × L`, where `L` is the canonical bounding-box diagonal. An inconsistent inverse blocks the geometry result even when all observed vertices lie in a plane unaffected by the inconsistency. Reflections require winding review; faces are not automatically reversed.

```python
from mesh_diagnostics import diagnose_mesh

report = diagnose_mesh(
    [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
    [(0, 1, 2)],
)
assert report.geometry_valid
assert report.within_runtime_budget
assert report.component_triangle_counts == (1,)
private_receipt = report.as_dict()
```

## Report interpretation

The immutable `mesh-diagnostics-v1` report separates three concerns:

| Field | Meaning |
|---|---|
| `geometry_valid`, `blocking_reasons` | The implemented position/index/area/bounds/transform checks pass, together with supplied-normal shape/finiteness checks. This is a subset of mesh validity. |
| `target_met`, `within_runtime_budget` | Source triangle count meets the [adopted target 50,000 and maximum 100,000](image-to-playable-validation.md#reconstruction-and-mesh-preparation). Invalid triangles still count. Budget pass/fail is independent of geometry validity. |
| `review_reasons` | Detached components, unused vertices, reflection, assumed canonical coordinates or exceeding the target require attention. They do not automatically discard authored accessories or reject geometry. |

Positions must have finite nonzero canonical bounds. If any position is invalid, the report withholds partial bounds and round-trip values. Overflowed derived values are unavailable rather than serialized as NaN/Infinity; callers can use strict JSON serialization. Diagnostic indices and transform metadata belong in a private receipt unless separately sanitized for publication.

Repeated-index and collinear triangles fail. `minimum_relative_area` is explicit triangle area divided by `L²`, default zero: reject exactly zero area without an invented thin-triangle threshold. A supplied nonnegative tolerance is recorded and compared in normalized coordinates. Floating arithmetic can lose distinctions near degeneracy or at extreme coordinate ranges; it cannot prove exact topology. Nonfinite bounding-box calculations block validity.

Components contain only structurally valid, nondegenerate triangles connected by an identical indexed edge. Point contact does not connect surfaces, and coincident positions with different indices are not welded. UV/material seams can therefore appear disconnected; a future format adapter must preserve/document its chosen indexing. Component triangle counts are sorted descending and do not identify anatomical regions. Unreferenced vertices are those absent from any structurally valid face, including degenerate faces.

The implementation uses O(vertices + triangles) memory. It accepts trusted internal arrays; it is not a new file parser or public request boundary. Custom positive triangle budgets are supported and recorded, with target ≤ maximum. A caller must apply its accepted profile rather than lowering a threshold to turn a failed case into a pass.

## Validation and remaining work

Authored synthetic numerical fixtures cover invalid indices and rows, nonfinite inputs/derived values, degenerate faces, edge/point/seam connectivity, detached-part preservation, empty geometry, exact budget boundaries, immutable inputs/reports, affine coordinate conversion, inverse consistency and scale-normalized round trips. The first test run failed on the absent module before implementation. They run in the normal configured CPU suite; no assets or inference are required.

No application endpoint, UI, GPU lifecycle, model, native export or existing parser changes in this increment. Browser/API, Blender and CUDA acceptance are not applicable to this unexposed logic. Those checks remain required when an adapter later integrates it into the affected pipeline. Passing these fixtures does not establish CUDA behavior, model quality or runtime performance.

Self-intersections, manifoldness, duplicate faces, physical normal direction, materials/colors/UVs, fused or missing limbs, joint topology, silhouette, weight transfer and deformation are not checked. The existing `mesh_runtime.validate_glb` remains the self-contained export/appearance boundary. Native reconstruction workers retain their current cleaning/component policies. Future integration must combine format validation, these diagnostics and [visual/anatomical acceptance](image-to-playable-validation.md), preserving immutable source-to-derivative provenance.
