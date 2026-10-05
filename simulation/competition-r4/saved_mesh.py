"""Restore the committed discretisation, without regenerating or morphing it.

The checkpoint and paired mesh must agree exactly. Physical inputs are checked
separately by the solver. This route is opt-in and never clears material state.
"""
from pathlib import Path
import json
import numpy as np


def same_relative_geometry(saved_label, current_path):
    """Only Windows separators are translated; no path/physics substitution."""
    saved=Path(str(saved_label).replace('\\','/'))
    current=Path(current_path)
    if saved.is_absolute() or current.is_absolute() or '..' in saved.parts or '..' in current.parts:
        raise ValueError('resume geometry must keep the repository-relative path')
    if saved.as_posix()!=current.as_posix() or not current.is_file():
        raise ValueError('checkpoint and current STEP paths identify different geometry')
    return True


def validate_state(cp, nodes, elements, links, tool_cells=None):
    """Inspect every saved member and required nonlinear-state shape."""
    shapes={
        'u':(3*nodes,), 'plastic':(elements,6), 'eqp':(elements,),
        'ref':(elements,6), 'stress':(elements,6), 'temp':(nodes,),
        'active':(elements,), 'thermal_active':(elements,), 'peak':(elements,),
        'peak_active':(elements,), 'peaknode':(nodes,),
        'last_mechanical_temperature':(elements,), 'observed_hot':(elements,),
        'sampled_hot':(elements,), 'link_reference':(links,3),
        'mechanical_link_active':(links,)}
    if tool_cells is not None:shapes['tool_temperature']=(tool_cells,)
    for key,shape in shapes.items():
        if key not in cp or cp[key].shape!=shape:
            raise ValueError(f'checkpoint state shape mismatch: {key}')
    for key in cp.files:
        member=cp[key]
        if member.dtype.kind in 'fc' and not np.isfinite(member).all():
            raise ValueError(f'nonfinite saved state: {key}')
    if np.any(cp['eqp']<0):raise ValueError('negative accumulated plastic strain')
    meta=json.loads(str(cp['metadata']))
    if not meta['struct'] or meta['t']!=meta['last_struct_t'] or meta['t']!=meta['struct'][-1][0]:
        raise ValueError('checkpoint is not a committed mechanical increment')
    if meta['struct'][-1][2]>=.05:
        raise ValueError('checkpoint mechanical equilibrium did not converge')
    return meta


def load_saved_mesh(path, checkpoint_path, initial_bore, seat_path):
    path, checkpoint_path = Path(path), Path(checkpoint_path)
    if not Path(seat_path).is_file():
        raise ValueError('the physical seat STEP is missing')
    with np.load(path, allow_pickle=False) as data:
        required = ('x', 'e', 'material', 'boundary', 'link_nodes', 'link_weights')
        if any(k not in data for k in required):
            raise ValueError('saved mesh is missing region/interface data')
        a = {k: data[k].copy() for k in required}
    x, e, m, bd, ln, lw = (a[k] for k in required)
    with np.load(checkpoint_path, allow_pickle=False) as cp:
        if not np.array_equal(cp['x'], x) or not np.array_equal(cp['e'], e):
            raise ValueError('saved mesh does not match the committed checkpoint')
        meta = json.loads(str(cp['metadata']))
        if meta['inputs']['initial_bore_diameter_mm'] != initial_bore:
            raise ValueError('saved bore is a different manufacturing point')
        same_relative_geometry(meta['inputs']['seat_geometry'],seat_path)
    if x.ndim != 2 or x.shape[1] != 3 or not np.isfinite(x).all():
        raise ValueError('invalid saved coordinates')
    for elements, width in ((e, 4), (bd, 3), (ln, ln.shape[1])):
        if elements.ndim != 2 or elements.shape[1] != width or not np.issubdtype(elements.dtype, np.integer):
            raise ValueError('invalid saved connectivity')
        if elements.min() < 0 or elements.max() >= len(x):
            raise ValueError('saved connectivity is outside the node set')
    if m.shape != (len(e),) or set(np.unique(m)) != {0, 1, 2}:
        raise ValueError('saved material partition is not the three-solid model')
    if lw.shape != ln.shape or not np.isfinite(lw).all() or not np.array_equal(lw[:, 0], np.ones(len(lw))):
        raise ValueError('invalid saved interface weights')
    if np.max(abs(lw.sum(axis=1))) > 1e-10:
        raise ValueError('saved interface does not reproduce translation')
    if np.max(abs(np.einsum('ij,ijk->ik', lw, x[ln]))) > 1e-8:
        raise ValueError('saved interface does not reproduce coordinates')
    determinants = np.linalg.det((x[e[:, 1:]] - x[e[:, :1]]).transpose(0, 2, 1))
    if not np.isfinite(determinants).all() or np.any(abs(determinants) <= 1e-12):
        raise ValueError('saved tetrahedron has zero volume')
    faces = np.sort(np.vstack([e[:, [0, 1, 2]], e[:, [0, 1, 3]], e[:, [0, 2, 3]], e[:, [1, 2, 3]]]), axis=1)
    exterior, count = np.unique(faces, axis=0, return_counts=True)
    exterior = exterior[count == 1]
    actual = np.sort(bd, axis=1)
    actual = actual[np.lexsort(actual.T[::-1])]
    if not np.array_equal(actual, exterior):
        raise ValueError('saved thermal boundary differs from the solid exterior')
    seat_nodes = np.unique(e[m == 1])
    radius = np.linalg.norm(x[seat_nodes, :2], axis=1)
    bore = abs(radius-initial_bore/2)<1e-4
    if not bore.any() or radius.min()<initial_bore/2-1e-4:
        raise ValueError('saved bore coordinates do not match the input diameter')
    links = [(int(row[0]), row[1:].copy(), -weights[1:].copy()) for row, weights in zip(ln, lw)]
    return x, e, m, bd, links
