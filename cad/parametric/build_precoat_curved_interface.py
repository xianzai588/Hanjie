"""Nominal physical pocket and conformal first-layer machining interface."""
from pathlib import Path
import json
import math
import gmsh

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'cad/generated/independent-precoat-curved'


def run():
    if (OUT/'geometry-audit.json').exists():
        raise ValueError('Preserve completed design geometry')
    OUT.mkdir(parents=True, exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.model.add('QT-conformal-precoat')
        occ = gmsh.model.occ
        seat = occ.importShapes(str(ROOT/'simulation/competition-r4/geometry/8P-R2-t15.step'))
        occ.translate(seat, 0, 0, 100)
        original_volume = sum(occ.getMass(*ent) for ent in seat if ent[0] == 3)
        inner, outer, top, depth, radius, first = 68.98, 74.98, 115., 1.5, 1.5, .7
        centre_r, centre_z = inner+radius, top-depth+radius
        def pocket(offset):
            r = radius-offset
            p = [occ.addPoint(*q) for q in [(centre_r-r,0,top), (outer,0,top),
                                           (outer,0,centre_z-r), (centre_r,0,centre_z-r)]]
            centre = occ.addPoint(centre_r,0,centre_z)
            edges = [occ.addLine(p[i],p[i+1]) for i in range(3)]
            edges.append(occ.addCircleArc(p[3],centre,p[0]))
            surface = occ.addPlaneSurface([occ.addCurveLoop(edges)])
            ring = [ent for ent in occ.revolve([(2,surface)],0,0,0,0,0,1,2*math.pi) if ent[0]==3]
            patches, _ = occ.intersect(ring,seat,removeObject=True,removeTool=False)
            return [ent for ent in patches if ent[0]==3]
        full = pocket(0.)
        second = pocket(first)
        first_solids, _ = occ.cut(full, second, removeObject=True, removeTool=False)
        first_solids = [ent for ent in first_solids if ent[0]==3]
        if len(first_solids)!=8 or len(second)!=8:
            raise RuntimeError('Each layer must contain eight actual wing patches')
        entities, mapping = occ.fragment(seat, first_solids+second)
        occ.synchronize()
        def ids(start, count):
            return {tag for group in mapping[start:start+count] for dim,tag in group if dim==3}
        one, two = ids(len(seat),8), ids(len(seat)+8,8)
        qt = ids(0,len(seat))-one-two
        groups = {'QT450-10':qt,'first_CI_A1':one,'second_bare_Ni99':two}
        if not all(groups.values()) or one & two or qt & (one|two):
            raise RuntimeError('Ambiguous material partition')
        volumes = {name:sum(occ.getMass(3,tag) for tag in tags) for name,tags in groups.items()}
        closure = sum(volumes.values())-original_volume
        # Curved OCC surface integrals have finite quadrature precision.
        # This numerical closure is not a machining or strength allowance.
        if abs(closure)/original_volume>1e-7:
            raise RuntimeError(f'Layer volume closure {closure:g} mm3; {volumes}; original {original_volume:g} mm3')
        boundaries = {name:{tag for solid in tags for dim,tag in gmsh.model.getBoundary([(3,solid)],False,False)
                            if dim==2} for name,tags in groups.items()}
        bypass = boundaries['QT450-10'] & boundaries['second_bare_Ni99']
        if bypass:
            raise RuntimeError('Second layer directly touches QT on a finite surface')
        first_interface = boundaries['QT450-10'] & boundaries['first_CI_A1']
        layer_interface = boundaries['first_CI_A1'] & boundaries['second_bare_Ni99']
        for number,(name,tags) in enumerate(groups.items(),1):
            group = gmsh.model.addPhysicalGroup(3,sorted(tags),number)
            gmsh.model.setPhysicalName(3,group,name)
        gmsh.write(str(OUT/'precoat-stack-R15-R08.step'))
        gmsh.write(str(OUT/'precoat-stack-R15-R08.brep'))
        audit = dict(source_seat='simulation/competition-r4/geometry/8P-R2-t15.step',
                     pocket_depth_mm=depth, first_flat_retained_mm=first,
                     QT_corner_radius_mm=radius, first_machining_corner_radius_mm=radius-first,
                     inner_radius_mm=inner, outer_radius_mm=outer, finished_z_mm=top,
                     nominal_original_seat_volume_mm3=original_volume, material_volumes_mm3=volumes,
                     replacement_volume_error_mm3=closure, replacement_relative_volume_error=abs(closure)/original_volume,
                     geometric_integration_relative_tolerance=1e-7,
                     material_volume_tags={k:sorted(v) for k,v in groups.items()},
                     QT_first_geometric_interface_area_mm2=sum(occ.getMass(2,tag) for tag in first_interface),
                     first_second_geometric_interface_area_mm2=sum(occ.getMass(2,tag) for tag in layer_interface),
                     second_QT_shared_face_area_mm2=sum(occ.getMass(2,tag) for tag in bypass),
                     conformal_nominal_geometry_pass=True, fusion_assigned=False, PMZ_capacity_assigned=False,
                     scope='Nominal R1.5 pocket and 0.7mm normal-offset first layer; geometric surfaces are not proven fused areas. Depth/thickness tolerance family and thermomechanical birth/machining remain to be computed.')
        (OUT/'geometry-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
        print(json.dumps(audit,indent=2))
    finally:
        gmsh.finalize()


if __name__=='__main__':
    run()
