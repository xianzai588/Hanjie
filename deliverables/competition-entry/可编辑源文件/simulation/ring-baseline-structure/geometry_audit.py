"""Verify the actual straight-sided shell facets preserve the unwelded gap.

Corner radii and facet centroids alone do not bound the sagitta.  Each inner
shell triangle is clipped to the ring height, and the shortest radius on the
clipped polygon edges is calculated.  The entire ring lies inside R=74.98.
"""
import numpy as np


def _clip_z(polygon, height, keep_above):
    output = []
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        aa = a[2] >= height if keep_above else a[2] <= height
        bb = b[2] >= height if keep_above else b[2] <= height
        if aa:
            output.append(a)
        if aa != bb:
            output.append(a + (height-a[2])/(b[2]-a[2])*(b-a))
    return np.asarray(output).reshape(-1, 3)


def audit_unwelded_gap(mesh, *, reject=False):
    p = mesh["points"]
    tri = mesh.get("triangles6", mesh.get("triangles"))[:, :3]
    tet = mesh.get("tetrahedra10", mesh.get("tetrahedra"))
    mids = mesh["material_ids"]
    face = p[tri]
    inner = face[np.all(abs(np.linalg.norm(face[:, :, :2], axis=2)-75.) < 1e-6, axis=1)]
    minimum = float("inf")
    tested = 0
    for triangle in inner:
        polygon = _clip_z(_clip_z(triangle, 100., True), 115., False)
        if not len(polygon):
            continue
        tested += 1
        for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
            v = b[:2]-a[:2]
            t = np.clip(-a[:2]@v/(v@v), 0., 1.) if v@v > 1e-30 else 0.
            minimum = min(minimum, float(np.linalg.norm(a[:2]+t*v)))
    shell = np.unique(tet[mids == 2])
    precoat = np.unique(tet[np.isin(mids, [1, 3, 4])])
    shared = len(np.intersect1d(shell, precoat))
    passed = tested > 0 and minimum > 74.98+1e-8 and shared == 0
    result = {
        "method": "clip actual straight inner-shell triangular facets to z100..115; minimize xy radius on every polygon edge",
        "tested_facets": tested,
        "minimum_faceted_shell_inner_radius_in_z100_115_mm": minimum,
        "maximum_nominal_seat_outer_radius_mm": 74.98,
        "minimum_conservative_open_clearance_mm": minimum-74.98,
        "direct_precoated_seat_shell_shared_nodes": shared,
        "unwelded_gap_geometry_verified": bool(passed),
    }
    if reject and not passed:
        raise RuntimeError(f"Mesh does not preserve the unwelded gap: {result}")
    return result
