"""Classical 3D elastic eigenstrain kernels with all manufacturing fixtures removed.

Input amplitude is intentionally not inferred from a temperature peak.  The
precoat kernels are *changes* in retained eigenstrain during final welding:
unknown precoat residual stress is an independent qualification input.  This is
an admissible-response window, not a simulated manufacturing residual state.
"""
from __future__ import annotations
import json
import hashlib
import sys
import time
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import cg
from scipy.interpolate import LinearNDInterpolator
from skfem import MeshTet,Basis,ElementVector,ElementTetP1,asm
from skfem.models.elasticity import linear_elasticity
import pyamg
import yaml
from threadpoolctl import threadpool_limits
from run_ring_manufacturing import HERE,ROOT,build_mesh,validated_process,operators,section_axis_envelope,fit_position_diameter
from geometry_audit import audit_unwelded_gap

MATERIALS={1:(169000.,.27),2:(206000.,.30),3:(200000.,.30),4:(200000.,.30),5:(200000.,.30)}
UNIT=1e-4


def measure(x,u):
    radius=np.linalg.norm(x[:,:2],axis=1)
    def sample(r,zs,count):
        mask=abs(radius-r)<1e-5;angle=np.arctan2(x[mask,1],x[mask,0]);co=np.column_stack((angle,x[mask,2]));val=u[mask]
        co=np.vstack((co-[2*np.pi,0],co,co+[2*np.pi,0]));val=np.vstack((val,val,val))
        ip=LinearNDInterpolator(co,val)
        tt=np.tile(np.arange(count)*2*np.pi/count,len(zs));zz=np.repeat(zs,count)
        du=ip(np.c_[tt,zz])
        if not np.isfinite(du).all():raise RuntimeError('missing metrology surface')
        return np.c_[r*np.cos(tt),r*np.sin(tt),zz]+du
    bottom=abs(x[:,2])<1e-5
    ip=LinearNDInterpolator(x[bottom,:2],u[bottom]);a=np.arange(96)*2*np.pi/96
    xy=np.c_[77.5*np.cos(a),77.5*np.sin(a)];adu=ip(xy)
    if not np.isfinite(adu).all():raise RuntimeError('missing A sample')
    A=np.c_[xy,np.zeros(96)]+adu;B=sample(75,[20,180],96);bore=sample(20,np.linspace(100,115,17),192)
    fit=fit_position_diameter(A,B,bore);fit.update(section_axis_envelope(A,B,bore,17,192))
    fit['position_diameter_mm']=max(fit['position_diameter_mm'],fit['section_axis_envelope_diameter_mm'])
    fit['minimum_diameter_change_um']=(fit['sampled_bore_two_point_diameter_min_mm']-40)*1000
    fit['maximum_diameter_change_um']=(fit['sampled_bore_two_point_diameter_max_mm']-40)*1000
    fit['position_diameter_um']=fit['position_diameter_mm']*1000
    return fit


def run(level,key_only=False,snapshot_path=None):
    folder=HERE/'results'/level;folder.mkdir(parents=True,exist_ok=True)
    validated_process()
    snapshot=Path(snapshot_path) if snapshot_path is not None else ROOT/'simulation/ring-baseline-structure/results'/('p1-current-coarse-safe' if level=='coarse' else level)
    original=dict(np.load(snapshot/'mesh.npz'))
    summary=json.loads((snapshot/'mesh-summary.json').read_text())
    source_result=json.loads((snapshot/('support-inputs.json' if (snapshot/'support-inputs.json').exists() else 'result.json')).read_text())
    source_inputs=source_result if 'mesh_inputs' in source_result else source_result.get('analysis_inputs')
    cad=(ROOT/'cad/generated/ring-baseline/ring-precoat-eight-windows-17solids.step').read_text()
    data_sha=hashlib.sha256(''.join(cad.split('DATA;',1)[1].split('ENDSEC;',1)[0].split()).encode()).hexdigest()
    if source_inputs is not None:
        mesh_inputs=source_inputs['mesh_inputs']
        if mesh_inputs['precoat_STEP_geometry_sha256']!=data_sha or mesh_inputs['effective_length_mm']!=18. or mesh_inputs['leg_mm']!=3.5:
            raise RuntimeError('structural snapshot identity differs from current retained CAD/support geometry')
        if source_inputs['process_version']!=validated_process()['version']:raise RuntimeError('structural snapshot process version differs')
    source_materials=source_result['material_inputs']
    if any((source_materials[str(mid)]['E_MPa'],source_materials[str(mid)]['nu'])!=value for mid,value in MATERIALS.items()):
        raise RuntimeError('cold kernels and service structure material inputs differ')
    gap_audit=audit_unwelded_gap(original,reject=True)
    if summary['effective_segment_length_mm']!=18. or summary['fillet_leg_mm']!=3.5:raise RuntimeError('minimum effective support mesh mismatch')
    x,e,m=original['points'],original['tetrahedra'],original['material_ids']
    radial=np.linalg.norm(x[:,:2],axis=1)
    if not (np.any(abs(radial-20)<1e-5) and np.any((abs(radial-75)<1e-5)&(abs(x[:,2]-200)<1e-5))):raise RuntimeError('snapshot object dimensions mismatch')
    _,snapshot_vol,_,_=operators(x,e,False)
    expected=json.loads((ROOT/'cad/generated/ring-baseline/ring-precoat-design.json').read_text())['geometry']['retained_material_volumes_mm3']
    target={1:expected['QT450-10'],3:expected['first_CI_A1_retained'],4:expected['second_Ni_retained']}
    errors={str(mid):abs(float(snapshot_vol[m==mid].sum())-value)/value for mid,value in target.items()}
    if max(errors.values())>.05:raise RuntimeError('frozen support mesh differs from current17-solid retained-material object')
    summary={**summary,'bulk_mm':summary['bulk_size_mm'],'cold_effective_support_mm':18.,'actual_thermal_path_mm':20.,
      'interface_method':'conforming nominal shared faces; minimum18mm effective support and3.5mm fillet',
      'snapshot_provenance':'explicit fixed accepted P1 structural mesh; not a claim of rebuilding with latest builder settings',
      'original_analysis_inputs':source_inputs,'original_cache_identity_available':source_inputs is not None,
      'actual_faceted_gap_audit':gap_audit,
      'current_precoat_STEP_DATA_sha256':data_sha,'source_mesh_npz_sha256':hashlib.sha256((snapshot/'mesh.npz').read_bytes()).hexdigest(),
      'source_snapshot':str(snapshot.relative_to(ROOT)),'current_retained_volume_relative_error':errors}
    start=time.time();mesh=MeshTet(x.T,e.T,sort_t=False);basis=Basis(mesh,ElementVector(ElementTetP1()),intorder=1)
    g,vol,b,dof=operators(x,e,True)
    K=None
    D=np.zeros((len(e),6,6));pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3
    for mid,(E,nu) in MATERIALS.items():
        ix=m==mid;lam,mu=E*nu/((1+nu)*(1-2*nu)),E/(2*(1+nu))
        kb=asm(linear_elasticity(lam,mu),basis.with_elements(np.flatnonzero(ix)))
        K=kb if K is None else K+kb
        D[ix]=3*(lam+2*mu/3)*pv+2*mu*(np.eye(6)-pv)
    # Six coordinate-gauge DOFs only: no mandrel, pads, press, copper load or
    # shell-bottom clamp.  Gauge reactions are audited and must be negligible.
    bottom=np.flatnonzero(abs(x[:,2])<1e-5)
    anchors=[bottom[np.argmin(np.linalg.norm(x[bottom,:2]-[77.5*np.cos(a),77.5*np.sin(a)],axis=1))] for a in (0,2*np.pi/3,4*np.pi/3)]
    fixed=np.array([3*anchors[0],3*anchors[0]+1,3*anchors[0]+2,3*anchors[1]+1,3*anchors[1]+2,3*anchors[2]+2]);free=np.setdiff1d(np.arange(K.shape[0]),fixed)
    kfree=K[free,:][:,free].tocsr();modes=np.zeros((K.shape[0],6));modes.reshape(-1,3,6)[:,:,:3]=np.eye(3)
    for axis in range(3):modes[:,axis+3]=np.cross(np.eye(3)[axis],x-x.mean(axis=0)).ravel()/160
    ml=pyamg.smoothed_aggregation_solver(kfree,B=modes[free],symmetry='symmetric',max_coarse=250,max_levels=10)
    precon=ml.aspreconditioner();c=x[e].mean(axis=1);theta=np.arctan2(c[:,1],c[:,0]);seg=np.rint(theta/(np.pi/4)).astype(int)%8
    modespec={
        'symmetric_final_shrink':np.where(m==5,-UNIT,0.),
        'first_harmonic_final_shrink':np.where(m==5,-UNIT*np.cos(seg*np.pi/4),0.),
        'second_harmonic_final_shrink':np.where(m==5,-UNIT*np.cos(seg*np.pi/2),0.),
        'single_segment_final_shrink':np.where((m==5)&(seg==0),-UNIT,0.),
        'first_harmonic_precoat_redistribution':np.where((m==3)|(m==4),-UNIT*np.cos(seg*np.pi/4),0.),
        'single_window_precoat_redistribution':np.where(((m==3)|(m==4))&(seg==0),-UNIT,0.),
    }
    if key_only:
        modespec={k:v for k,v in modespec.items() if k in ('symmetric_final_shrink','first_harmonic_final_shrink','first_harmonic_precoat_redistribution')}
    responses={};fields={};stress_fields={}
    for name,values in modespec.items():
        eigen=np.zeros((len(e),6));eigen[:,:3]=values[:,None]
        stress0=np.einsum('eij,ej->ei',D,eigen)
        ef=np.einsum('eji,ej,e->ei',b,stress0,vol)
        F=np.bincount(dof.ravel(),weights=ef.ravel(),minlength=K.shape[0]);it=[0]
        def callback(u):it[0]+=1
        ur,info=cg(kfree,F[free],M=precon,rtol=1e-9,atol=1e-8,maxiter=3000,callback=callback)
        if info:raise RuntimeError(f'CG {name} failed {info}')
        U=np.zeros(K.shape[0]);U[free]=ur;res=K@U-F;u=U.reshape(-1,3)
        strain=np.einsum('eij,ej->ei',b,U[dof])-eigen;stress=np.einsum('eij,ej->ei',D,strain)
        dev=stress-stress@pv;vm=np.sqrt(1.5*np.sum(dev*dev,axis=1))
        metrics=measure(x,u);responses[name]=dict(input_amplitude=UNIT,input_microstrain=UNIT*1e6,CG_iterations=it[0],free_residual_N=float(np.linalg.norm(res[free])),
          gauge_reaction_N=float(np.linalg.norm(res[fixed])),maximum_von_Mises_MPa=float(vm.max()),von_Mises_by_material_MPa={str(mid):float(vm[m==mid].max()) for mid in MATERIALS},**metrics)
        fields[name]=u;stress_fields[name]=stress
        print('cold_response',level,name,metrics['position_diameter_um'],metrics['minimum_diameter_change_um'],metrics['maximum_diameter_change_um'],flush=True)
    # Scan a declared independent range; it is not an assertion that the real
    # pWPS produces any particular point inside this range.
    scans=[]
    for mean in (0.,100.,300.,500.,1000.):
        for harmonic in (0.,10.,25.,50.,100.,200.):
            for precoat in (0.,25.,100.,200.):
                u=(mean/100.*fields['symmetric_final_shrink']+harmonic/100.*fields['first_harmonic_final_shrink']+precoat/100.*fields['first_harmonic_precoat_redistribution'])
                # Axis and diameter depend linearly at these micrometre motions;
                # compute actual dense sampled diameters for every combined state.
                metrics=measure(x,u)
                combined_stress=(mean/100.*stress_fields['symmetric_final_shrink']+harmonic/100.*stress_fields['first_harmonic_final_shrink']+precoat/100.*stress_fields['first_harmonic_precoat_redistribution'])
                dev=combined_stress-combined_stress@pv;combined_vm=np.sqrt(1.5*np.sum(dev*dev,axis=1))
                low=40.-metrics['minimum_diameter_change_um']/1000
                high=40.025-metrics['maximum_diameter_change_um']/1000
                scans.append(dict(mean_final_shrink_microstrain=mean,first_harmonic_final_shrink_microstrain=harmonic,
                  first_harmonic_precoat_redistribution_microstrain=precoat,position_diameter_um=metrics['position_diameter_um'],
                  minimum_diameter_change_um=metrics['minimum_diameter_change_um'],maximum_diameter_change_um=metrics['maximum_diameter_change_um'],
                  initial_bore_allowable_low_mm=low,initial_bore_allowable_high_mm=high,
                  mathematical_position_within_13_5um=metrics['position_diameter_um']<=13.5,nonempty_bore_window=low<=high,combined_maximum_von_Mises_MPa=float(combined_vm.max()),
                  combined_VM_by_material_MPa=json.dumps({str(mid):float(combined_vm[m==mid].max()) for mid in MATERIALS}),material_feasibility_established=False))
    result=dict(mesh=summary,process_version=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())['version'],actual_path_320mm=True,
      model='3D cold linear-elastic eigenstrain response, nominal assumed bonded connections, full fixture release',
      elastic_inputs={str(k):dict(E_MPa=v[0],nu=v[1]) for k,v in MATERIALS.items()},kernel_amplitude=UNIT,
      cold_support_scope='8x18mm minimum effective support;3.5mm fillet. Thermal calculations use the20mm actual arc/deposit envelope. Neither qualified first interface nor20mm full support is presumed.',source_qualification='input eigenstrains are independent sensitivity variables; no temperature-to-shrinkage calibration is claimed',
      retained_precoat_policy='No complete precoat residual-stress/plastic field is imported. The nonzero kernels represent final-cycle changes of retained eigenstrain, not numerical inheritance of that field. Predictive manufacturing response requires the complete retained precoat state.',
      responses=responses,conditional_scans=scans,key_modes_only=key_only,
      material_capacity_assigned=False,cold_elastic_applicability='Each100microstrain kernel has its own per-material stress; combined stresses must be checked against qualified yield data before using the linear response. Neither a mathematical position bound nor low axis drift establishes deposited-layer strength.',
      cold_position_budget_um=13.5,metrology='A96 at R77.5; B96 at z20/180; bore17x192; straight-axis and section-centre envelope',
      elastic_only=True,full_manufacturing_chain_passed=False,elapsed_s=time.time()-start)
    (folder/'cold-response.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));np.savez_compressed(folder/'cold-response-fields.npz',**fields)
    import csv
    with (folder/'conditional-window.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(scans[0]));writer.writeheader();writer.writerows(scans)
    return result

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--level',choices=['coarse','medium'],default='coarse');ap.add_argument('--key-only',action='store_true');ap.add_argument('--snapshot',type=Path);a=ap.parse_args()
    with threadpool_limits(limits=1):run(a.level,a.key_only,a.snapshot)
