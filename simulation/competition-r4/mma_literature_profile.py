"""CI-A1 enthalpy and a bounded, literature-anchored one-wing study."""
from pathlib import Path
import copy,csv,json
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def configure(tables,product='CI-A1'):
    rows=list(csv.DictReader((ROOT/'simulation/competition-r4/results/mma-filler-enthalpy-20261006/enthalpy.csv').open(encoding='utf8')))
    rows=[r for r in rows if r['product']==product and r['graphite_allowed']=='True']
    t=np.array([float(r['T_C']) for r in rows]);h=np.array([float(r['delta_H_J_kg']) for r in rows])
    liquid=np.array([float(r['liquid_mass_fraction']) for r in rows])
    slope=np.diff(h)/np.diff(t)
    if np.min(slope)<=0:raise ValueError('Non-monotone checked CI-A1 enthalpy')
    offset=5*slope[0]
    t=np.r_[20,t,2800.];h=np.r_[0,h+offset,h[-1]+offset+800*slope[-1]]
    cp=np.diff(h)/np.diff(t)
    out=copy.deepcopy(tables);ni=out[3]
    ni['name']=product+' undiluted deposited chemistry; mixing not solved'
    ni['nominal_properties_20c']['density_kg_m3']=8890. if product=='CI-A1' else 8200.
    if product=='CI-A2':ni['temperature_dependent']=copy.deepcopy(out[2]['temperature_dependent'])
    ni['fusion_enthalpy']=dict(solidus_C=float(t[1:][np.flatnonzero(liquid>1e-6)[0]]),
        liquidus_C=float(t[1:][np.flatnonzero(liquid>1-1e-6)[0]]),latent_heat_J_kg=0.,
        basis='Gibbs-checked Fe-Ni-C total enthalpy already contains melting; no additional latent heat')
    ni['enthalpy_table']=dict(temperature_C=t.tolist(),relative20C_J_kg=h.tolist(),
        reference_offset_25_to20_J_kg=float(offset),
        basis='Author-TDB CI-A1, graphite allowed; Si/Mn omitted; 2000..2800 C uses last liquid cp slope; conductivity remains an engineering hypothesis')
    return out,t,h,cp


def mesh_saved(output,h=.65):
    import gmsh
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/'mesh.npz').exists():return
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0);occ=gmsh.model.occ
        occ.importShapes(str(ROOT/'cad/generated/mma-mass-envelope/CI-A1/first-mass-envelope.brep'));occ.synchronize()
        entities=occ.getEntities(3);qt=[tag for dim,tag in entities if occ.getMass(dim,tag)>10000]
        ni=[tag for dim,tag in entities if tag not in qt]
        surfaces=sorted(set(s[1] for tag in ni for s in gmsh.model.getBoundary([(3,tag)],False,False)))
        distance=gmsh.model.mesh.field.add('Distance');gmsh.model.mesh.field.setNumbers(distance,'FacesList',surfaces)
        gmsh.model.mesh.field.setNumber(distance,'Sampling',60)
        threshold=gmsh.model.mesh.field.add('Threshold')
        for k,v in dict(InField=distance,SizeMin=h,SizeMax=3.,DistMin=1.,DistMax=15.).items():gmsh.model.mesh.field.setNumber(threshold,k,v)
        gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        for k,v in [('Mesh.MeshSizeFromPoints',0),('Mesh.MeshSizeFromCurvature',0),('Mesh.MeshSizeExtendFromBoundary',0),('Mesh.MeshSizeMin',.8*h),('Mesh.MeshSizeMax',3.),('Mesh.MinimumCirclePoints',40)]:gmsh.option.setNumber(k,v)
        gmsh.model.mesh.generate(3)
        tags,xyz,_=gmsh.model.mesh.getNodes();index={int(t):i for i,t in enumerate(tags)}
        x=np.asarray(xyz).reshape(-1,3);elements=[];materials=[]
        for mat,group in [(1,qt),(3,ni)]:
            for tag in group:
                _,conn=gmsh.model.mesh.getElementsByType(4,tag)
                local=np.array([index[int(t)] for t in conn]).reshape(-1,4)
                elements.extend(local);materials.extend([mat]*len(local))
        e=np.array(elements);m=np.array(materials,np.int8);used=np.unique(e)
        remap=np.full(len(x),-1,int);remap[used]=np.arange(len(used));x=x[used];e=remap[e]
        np.savez_compressed(output/'mesh.npz',x=x,e=e,material=m)
        (output/'mesh-summary.json').write_text(json.dumps(dict(nodes=len(x),tetrahedra=len(e),h_mm=h,
            geometry='same mass-closed CI-A1 one-wing envelope on whole QT seat',
            full_manufacturing_mesh=False,physical_bead_shape_verified=False),indent=2),encoding='utf8')
        print('MMA mesh',len(x),len(e),flush=True)
    finally:gmsh.finalize()
