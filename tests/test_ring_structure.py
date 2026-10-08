"""Independent force/moment and metrology invariants for the ring FE inputs."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest


def ring_module():
    import sys
    path = Path(__file__).parents[1] / "simulation/ring-baseline-structure/run_ring_structure.py"
    spec = importlib.util.spec_from_file_location("ring_structure", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0,str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def cylinder_surface():
    theta = np.arange(24)*2*np.pi/24
    points = np.array([[20*np.cos(a),20*np.sin(a),z] for z in [100.,107.5,115.] for a in theta])
    triangles = []
    for k in range(2):
        for i in range(24):
            a=k*24+i; b=k*24+(i+1)%24; c=a+24; d=b+24
            triangles += [[a,b,c],[b,c,d]]
    return points, np.array(triangles)


def test_bore_load_matches_independent_force_and_moment_sums():
    module = ring_module(); points, triangles = cylinder_surface()
    for direction, target in [([1.,0.,0.],5000.),([0.,0.,1.],5000.),("moment",250000.)]:
        force=module.surface_load(points,triangles,direction,target)
        total=force.sum(axis=0)
        moment=np.cross(points-[0,0,107.5],force).sum(axis=0)
        if direction == "moment":
            np.testing.assert_allclose(total,0.,atol=1e-10)
            np.testing.assert_allclose(moment,[0.,target,0.],atol=1e-9)
        else:
            np.testing.assert_allclose(total,np.array(direction)*target,atol=1e-10)
            np.testing.assert_allclose(moment,0.,atol=1e-9)


def test_cylinder_metric_separates_axis_tilt_and_dilation():
    module=ring_module(); p,tri=cylinder_surface()
    center=np.array([.004,-.003])
    tilt=np.array([.0002,-.0001])
    radius_increment=.002
    u=np.zeros_like(p)
    u[:,:2]=center+(p[:,2]-107.5)[:,None]*tilt+radius_increment*p[:,:2]/20.
    metric=module.bore_metrics(p,u,tri)
    np.testing.assert_allclose(metric["axis_center_radial_um"],5.,atol=1e-10)
    np.testing.assert_allclose(metric["axis_tilt_urad"],np.sqrt(5)*100,atol=1e-10)
    np.testing.assert_allclose(metric["mean_bore_diameter_change_um"],4.,atol=1e-10)
    assert metric["cylindrical_radial_peak_to_valley_um"] < 1e-10


def test_changed_joint_inputs_cannot_reuse_an_old_result(tmp_path):
    module=ring_module()
    module.HERE=tmp_path
    out=tmp_path/"results"/"coarse"
    out.mkdir(parents=True)
    import json
    old=module.analysis_inputs("coarse",3.5)
    old["mesh_inputs"]["leg_mm"]=3.0
    (out/"result.json").write_text(json.dumps({"analysis_inputs":old}))
    with pytest.raises(RuntimeError,match="input identity differs"):
        module.solve("coarse",3.5)


def test_step_geometry_cache_ignores_export_header_time(tmp_path):
    module=ring_module();a=tmp_path/"a.step";b=tmp_path/"b.step"
    a.write_text("HEADER;FILE_NAME('2026-10-08');ENDSEC;DATA;#1=CARTESIAN_POINT('',(0,0,0));ENDSEC;")
    b.write_text("HEADER;FILE_NAME('2026-10-09');ENDSEC;DATA;#1=CARTESIAN_POINT('',(0,0,0));ENDSEC;")
    assert module.step_geometry_digest(a)==module.step_geometry_digest(b)
    b.write_text("HEADER;FILE_NAME('2026-10-09');ENDSEC;DATA;#1=CARTESIAN_POINT('',(1,0,0));ENDSEC;")
    assert module.step_geometry_digest(a)!=module.step_geometry_digest(b)


def test_quadratic_tetra_matches_affine_energy_and_rigid_rotation():
    import sys
    folder=Path(__file__).parents[1]/"simulation/ring-baseline-structure"
    sys.path.insert(0,str(folder))
    try:
        import run_quadratic_check as module
    finally:
        sys.path.pop(0)
    vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float)
    p=np.vstack([vertices,*[(vertices[a]+vertices[b])[None,:]/2 for a,b in module.EDGES]])
    mesh={"points":p,"tetrahedra10":np.arange(10)[None,:],"material_ids":np.array([1])}
    K,meta=module.assemble(mesh)
    displacement=p@np.array([[.001,0,0],[.002,.003,0],[0,0,-.001]])
    gradient=np.array([[.001,.002,0],[0,.003,0],[0,0,-.001]])
    strain=(gradient+gradient.T)/2
    E,nu=169000.,.27
    lam,mu=E*nu/((1+nu)*(1-2*nu)),E/(2*(1+nu))
    energy=(lam*np.trace(strain)**2/2+mu*np.sum(strain*strain))/6
    np.testing.assert_allclose(displacement.ravel()@K@displacement.ravel()/2,energy,rtol=1e-12)
    rotation=np.cross(np.broadcast_to([.03,-.02,.01],p.shape),p).ravel()
    assert abs(rotation@K@rotation) < 1e-10
    np.testing.assert_allclose(meta["integrated_quarter_volume_mm3"],1/6,rtol=1e-12)


def test_common_virtual_bore_sampling_preserves_affine_axis_response():
    import sys
    folder=Path(__file__).parents[1]/"simulation/ring-baseline-structure"
    sys.path.insert(0,str(folder))
    try:
        from bore_sampling import sample_surface
    finally:
        sys.path.pop(0)
    module=ring_module();p,tri=cylinder_surface()
    u=np.zeros_like(p);u[:,:2]=[.004,-.003]+(p[:,2]-107.5)[:,None]*[.0002,-.0001]
    q,v=sample_surface(p,tri,u,np.linspace(-np.pi,np.pi,128,endpoint=False),np.linspace(100.,115.,11),1)
    metric=module.bore_metrics(q,v,np.arange(len(q)))
    np.testing.assert_allclose(metric["axis_center_radial_um"],5.,atol=1e-10)
    np.testing.assert_allclose(metric["axis_tilt_urad"],np.sqrt(5)*100,atol=1e-10)
    assert metric["cylindrical_radial_peak_to_valley_um"]<1e-10


def test_gap_audit_checks_edge_sagitta_instead_of_only_centroid():
    ring_module()
    from geometry_audit import audit_unwelded_gap
    angle=np.arccos(.9997)
    p=np.array([[75*np.cos(angle),-75*np.sin(angle),100],
                [75*np.cos(angle),75*np.sin(angle),100], [75,0,115],
                [80,0,107], [70,0,100], [70,1,100], [69,0,100], [70,0,115]])
    mesh={"points":p,"triangles":np.array([[0,1,2]]),
          "tetrahedra":np.array([[0,1,2,3],[4,5,6,7]]),"material_ids":np.array([2,1])}
    assert np.linalg.norm(p[:3].mean(axis=0)[:2])>74.98
    audit=audit_unwelded_gap(mesh)
    assert audit["minimum_faceted_shell_inner_radius_in_z100_115_mm"]<74.98
    with pytest.raises(RuntimeError,match="does not preserve"):
        audit_unwelded_gap(mesh,reject=True)


def test_final_summary_cannot_relabel_an_old_process_version(tmp_path):
    import json
    import sys
    folder=Path(__file__).parents[1]/"simulation/ring-baseline-structure"
    sys.path.insert(0,str(folder))
    try:
        import summarize_quadratic as module
    finally:
        sys.path.pop(0)
    previous_here=module.HERE
    module.HERE=tmp_path
    try:
        for level in ("coarse","medium"):
            out=tmp_path/"results"/f"p2-linear-{level}"
            out.mkdir(parents=True)
            (out/"result.json").write_text(json.dumps({"process_version":"PREVIOUS-PROCESS"}))
            (out/"virtual-bore-summary.json").write_text("{}")
        with pytest.raises(RuntimeError,match="actual raw result process version"):
            module.main()
        assert not (tmp_path/"results/assessment.json").exists()
    finally:
        module.HERE=previous_here


def test_publication_identity_detects_same_version_material_change(monkeypatch):
    import json
    import sys
    folder=Path(__file__).parents[1]/"simulation/ring-baseline-structure"
    sys.path.insert(0,str(folder))
    try:
        import run_quadratic_check as module
    finally:
        sys.path.pop(0)
    raw=json.loads((folder/"results/p2-linear-medium/result.json").read_text())
    expected=module.current_publication_identity()
    assert expected["process_version"]==raw["process_version"]
    assert expected["input_identity"]==raw["input_identity"]
    monkeypatch.setitem(module.base.MATERIALS[1],"E_MPa",170000.)
    changed=module.current_publication_identity()
    assert changed["process_version"]==expected["process_version"]
    assert changed["input_identity"]!=raw["input_identity"]
    # The returned expectation is a snapshot, not a live view of MATERIALS.
    assert expected["input_identity"]==raw["input_identity"]
