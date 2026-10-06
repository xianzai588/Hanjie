"""Same pocketed QT solid, independent coarse mesh for oven warmup only."""
from pathlib import Path
import json
import gmsh
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'simulation/competition-r4/geometry/explicit-ni99-wing-t14-first07-h15-lh05/explicit-stack.brep'
OUT = ROOT/'simulation/competition-r4/geometry/design-precoat-warmup-coarse'


def run():
    if (OUT/'mesh.npz').exists():
        raise ValueError('Preserve completed mesh evidence')
    OUT.mkdir(parents=True, exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.model.add('independent-QT-warmup')
        imported = gmsh.model.occ.importShapes(str(SOURCE))
        solids = [ent for ent in imported if ent[0] == 3]
        seat = [ent for ent in solids if 100000 < gmsh.model.occ.getMass(*ent) < 200000]
        if len(seat) != 1:
            raise RuntimeError('Unique complete QT seat not found')
        nominal_volume = gmsh.model.occ.getMass(*seat[0])
        gmsh.model.occ.remove([ent for ent in solids if ent not in seat], recursive=True)
        gmsh.model.occ.synchronize()
        for key, value in {'Mesh.MeshSizeMin':2.4, 'Mesh.MeshSizeMax':2.4,
                           'Mesh.MeshSizeFromPoints':0, 'Mesh.MeshSizeFromCurvature':0,
                           'Mesh.MeshSizeExtendFromBoundary':0, 'Mesh.MinimumCirclePoints':100}.items():
            gmsh.option.setNumber(key, value)
        gmsh.model.mesh.generate(3)
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        lookup = {int(tag):i for i,tag in enumerate(tags)}
        _, connectivity = gmsh.model.mesh.getElementsByType(4, seat[0][1])
        e = np.array([lookup[int(tag)] for tag in connectivity]).reshape(-1,4)
        x = np.asarray(xyz).reshape(-1,3)
        used = np.unique(e); remap = np.full(len(x), -1, int); remap[used] = np.arange(len(used))
        x, e = x[used], remap[e]
        volume = np.abs(np.linalg.det(x[e[:,1:]]-x[e[:,0,None]]))/6
        error = float(abs(volume.sum()-nominal_volume)/nominal_volume)
        if error > .005:
            raise RuntimeError('Coarse QT geometric volume error exceeds0.5%')
        np.savez_compressed(OUT/'mesh.npz', x=x, e=e, material=np.ones(len(e), dtype=np.int8))
        audit = dict(source=str(SOURCE.relative_to(ROOT)), nominal_QT_volume_mm3=nominal_volume,
                     tetra_volume_mm3=float(volume.sum()), relative_volume_error=error,
                     nominal_mesh_size_mm=2.4, nodes=len(x), tetrahedra=len(e),
                     scope='Same BREP QT solid; no coatings or shell. Warmup convergence only, not a welding or residual-stress mesh.')
        (OUT/'geometry-audit.json').write_text(json.dumps(audit, indent=2), encoding='utf8')
        print(json.dumps(audit, indent=2))
    finally:
        gmsh.finalize()


if __name__ == '__main__':
    run()
