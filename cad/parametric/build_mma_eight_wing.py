"""Copy the same mass-closed first layer to all eight existing QT pockets."""
from pathlib import Path
import argparse
import json
import math
import gmsh
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def build(source, output, h):
    output.mkdir(exist_ok=True, parents=True)
    if (output/'geometry-audit.json').exists():
        raise ValueError('Preserve the saved eight-wing geometry')
    original = json.loads((source/'geometry-audit.json').read_text(encoding='utf8'))
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        occ = gmsh.model.occ
        entities = occ.importShapes(str(source/'first-mass-envelope.brep'))
        qt = [ent for ent in entities if ent[0]==3 and occ.getMass(*ent)>10000]
        ni = [ent for ent in entities if ent[0]==3 and ent not in qt]
        if len(qt)!=1 or not ni:
            raise RuntimeError('Source complete seat / one-wing deposit identification failed')
        all_ni = ni.copy()
        for sector in range(1, 8):
            copied = occ.copy(ni)
            occ.rotate(copied, 0,0,0, 0,0,1, sector*math.pi/4)
            all_ni.extend(copied)
        _, maps = occ.fragment(qt, all_ni)
        groups = {1:sorted({tag for dim,tag in maps[0] if dim==3}),
                  3:sorted({tag for mapped in maps[1:] for dim,tag in mapped if dim==3})}
        if set(groups[1])&set(groups[3]):
            raise RuntimeError('QT and deposited material overlap after conforming fragment')
        occ.synchronize()
        wing_volume = original['target_deposited_volume_one_wing_mm3']
        ni_volume = sum(occ.getMass(3, tag) for tag in groups[3])
        qt_volume = sum(occ.getMass(3, tag) for tag in groups[1])
        if abs(ni_volume-8*wing_volume)>1e-3:
            raise RuntimeError('Eight-wing mass closure failed')
        if abs(qt_volume-original['material_volumes_mm3']['QT'])>1e-3:
            raise RuntimeError('Copying deposits changed the machined QT seat')
        for number, tags in groups.items():
            gmsh.model.addPhysicalGroup(3,tags,number)
        gmsh.write(str(output/'first-mass-envelope.brep'))
        gmsh.write(str(output/'first-mass-envelope.step'))
        surfaces = sorted({s[1] for tag in groups[3] for s in gmsh.model.getBoundary([(3,tag)],False,False)})
        distance = gmsh.model.mesh.field.add('Distance')
        gmsh.model.mesh.field.setNumbers(distance, 'FacesList', surfaces)
        gmsh.model.mesh.field.setNumber(distance, 'Sampling', 60)
        threshold = gmsh.model.mesh.field.add('Threshold')
        for key,value in dict(InField=distance,SizeMin=h,SizeMax=3.,DistMin=1.,DistMax=15.).items():
            gmsh.model.mesh.field.setNumber(threshold,key,value)
        gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        for key,value in [('Mesh.MeshSizeFromPoints',0),('Mesh.MeshSizeFromCurvature',0),
                ('Mesh.MeshSizeExtendFromBoundary',0),('Mesh.MeshSizeMin',.8*h),('Mesh.MeshSizeMax',3.),('Mesh.MinimumCirclePoints',40)]:
            gmsh.option.setNumber(key,value)
        print('Mesh all eight actual deposition pockets',flush=True)
        gmsh.model.mesh.generate(3)
        tags,xyz,_ = gmsh.model.mesh.getNodes()
        index = {int(tag):i for i,tag in enumerate(tags)}
        x = np.asarray(xyz).reshape(-1,3)
        elements,materials = [],[]
        for number,tags in groups.items():
            for tag in tags:
                _,conn = gmsh.model.mesh.getElementsByType(4,tag)
                local = np.array([index[int(node)] for node in conn]).reshape(-1,4)
                elements.extend(local)
                materials.extend([number]*len(local))
        e = np.asarray(elements)
        m = np.asarray(materials,np.int8)
        used = np.unique(e)
        remap = np.full(len(x),-1,int)
        remap[used] = np.arange(len(used))
        x,e = x[used],remap[e]
        np.savez_compressed(output/'mesh.npz',x=x,e=e,material=m)
        audit = dict(original,geometry_state='all eight first-layer envelopes on unchanged pocketed QT; before any deposition or machining',
            one_wing_geometry_source=str(source),wing_count=8,nodes=len(x),tetrahedra=len(e),
            layer_mesh_h_mm=h,mesh_generated=True,total_first_volume_mm3=ni_volume,
            total_first_mass_g=ni_volume*8890e-6,
            total_mass_closure_error_g=(ni_volume-8*wing_volume)*8890e-6,
            material_volumes_mm3=dict(QT=qt_volume,MMA=ni_volume),
            physical_bead_shape_verified=False,residual_state_assigned=False,fusion_assigned=False)
        (output/'geometry-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(dict(nodes=len(x),tetrahedra=len(e),mass_g=audit['total_first_mass_g']),indent=2))
    finally:
        gmsh.finalize()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True)
    p.add_argument('--h',type=float,default=.65)
    a=p.parse_args()
    build(a.source,a.output,a.h)
