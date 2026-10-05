"""Functional metrology and conservative service screening of actual states."""
from pathlib import Path
import argparse,json
import numpy as np
from scipy.interpolate import LinearNDInterpolator
from postprocess import section_axis_envelope
from hanjie.simulation.structural_prep import fit_position_diameter

OUT=Path(__file__).parent/'results'


def shape(x,u,inp):
    radius=inp['initial_bore_diameter_mm']/2;rad=np.linalg.norm(x[:,:2],axis=1)
    count=384;sections=33;nd=192
    angles=np.arange(nd)*2*np.pi/nd;axy=np.c_[77.5*np.cos(angles),77.5*np.sin(angles)]
    bottom=x[:,2]<1e-5;adu=LinearNDInterpolator(x[bottom,:2],u[bottom])(axy)
    a=np.c_[axy,np.zeros(nd)]+adu
    def sample(r,zs,n,phase=0):
        pick=abs(rad-r)<1e-5;theta=np.arctan2(x[pick,1],x[pick,0]);coords=np.c_[theta,x[pick,2]]
        coords=np.vstack((coords-[2*np.pi,0],coords,coords+[2*np.pi,0]));values=np.vstack((u[pick],u[pick],u[pick]))
        tt=np.tile((np.arange(n)+phase)*2*np.pi/n,len(zs));zz=np.repeat(zs,n)
        disp=LinearNDInterpolator(coords,values)(np.c_[tt,zz])
        if not np.all(np.isfinite(disp)):raise ValueError('service metrology outside actual surface')
        return np.c_[r*np.cos(tt),r*np.sin(tt),zz]+disp
    if not np.all(np.isfinite(a)):raise ValueError('datum A outside actual annulus')
    b=sample(75,[20,180],nd);rows=[]
    for phase in (0,.5):
        hole=sample(radius,np.linspace(100,100+inp['seat_thickness_mm'],sections),count,phase)
        fit=fit_position_diameter(a,b,hole);fit.update(section_axis_envelope(a,b,hole,sections,count))
        fit['position_diameter_mm']=max(fit['position_diameter_mm'],fit['section_axis_envelope_diameter_mm'])
        rows.append(fit)
    keys=['position_diameter_mm','sampled_bore_two_point_diameter_min_mm','sampled_bore_two_point_diameter_max_mm','maximum_sampled_section_ovalization_mm']
    return {k:(min(r[k] for r in rows) if k.endswith('_min_mm') else max(r[k] for r in rows)) for k in keys}


def evaluate(case):
    folder=OUT/case
    required=['stateful-service-result.json','stateful-service-fields.npz','free-release-fields.npz']
    if any(not (folder/name).exists() for name in required):return dict(case=case,complete=False)
    result=json.loads((folder/required[0]).read_text(encoding='utf8'))
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    with np.load(folder/required[2]) as src:f={k:src[k] for k in src.files}
    with np.load(folder/required[1]) as src:s={k:src[k] for k in src.files}
    states=dict(cold=shape(f['x'],f['u'],inp),proof_loaded=shape(f['x'],f['u']+s['loaded_u_increment_mm'],inp),
        proof_unloaded=shape(f['x'],f['u']+s['unloaded_u_increment_mm'],inp))
    if 'operating_u_increment_mm' in s:states['operating']=shape(f['x'],f['u']+s['operating_u_increment_mm'],inp)
    # Conservative route: operating load must be elastic about the retained
    # manufacturing state. No uncalibrated percentage of plasticity is allowed.
    operating=[h for h in result['history'][:15] if abs(h['load_factor']-1)<1e-8]
    added=operating[0]['maximum_added_eqp'] if len(operating)==1 else None
    if 'operating_eqp' in s:added=float((s['operating_eqp']-f['eqp']).max())
    threshold=1e-10 # numerical zero, not an allowable material plastic strain
    increments={k:states['proof_unloaded'][k]-states['cold'][k] for k in states['cold']}
    budget=.028+.002+.0065+states['proof_unloaded']['position_diameter_mm']
    zones={}
    for j,name in enumerate(('Q235','QT','NiFe')):
        mask=f['material']==j;st=s['loaded_stress_Mandel_MPa'][mask]
        matrix=np.zeros((len(st),3,3));matrix[:,0,0]=st[:,0];matrix[:,1,1]=st[:,1];matrix[:,2,2]=st[:,2]
        # operators() uses [xx, yy, zz, sqrt2*yz, sqrt2*xz, sqrt2*xy].
        for index,(a,b) in enumerate(((1,2),(0,2),(0,1)),3):matrix[:,a,b]=matrix[:,b,a]=st[:,index]/np.sqrt(2)
        ultimate=inp['materials'][j]['nominal_properties_20c']['tensile_strength_mpa']
        principal=float(np.linalg.eigvalsh(matrix)[:,-1].max())
        zones[name]=dict(maximum_proof_tensile_principal_MPa=principal,nominal_bulk_ultimate_MPa=ultimate,
            bulk_tensile_screen_pass=principal<=ultimate)
    checks=dict(inherited_input_identical=result['input_snapshot']==inp,
        all_load_and_unload_steps_equilibrated=len(result['history'])==30 and all(h['residual_N']<.001 for h in result['history']),
        operating_elastic_about_retained_state=added is not None and added<=threshold,
        proof_unloaded_axis_budget_pass=budget<=.05,
        bulk_tensile_screen_pass=all(z['bulk_tensile_screen_pass'] for z in zones.values()),
        plastic_material_failure_basis_applicable=False,
        nonlinear_state_spatial_time_precision_pass=False)
    evidence=dict(case=case,complete=True,source_fields=required,input_snapshot=inp,metrology=states,
        unloaded_permanent_metric_changes_mm=increments,proof_unloaded_position_budget_mm=budget,
        operating_maximum_added_eqp=added,numerical_zero_eqp=threshold,
        maximum_added_eqp=result['maximum_added_eqp'],bulk_zones=zones,checks=checks,
        combined_bulk_strength_pass=all(checks.values()),
        scope='same bulk J2 and elastic interfaces; nominal bulk ultimate screen excludes Ni99 and QT PMZ; accepting finite operating plasticity requires an applicable failure and cyclic-stability basis, plus spatial/time refinement')
    (folder/'stateful-service-verification.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
    return evidence


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',nargs='+',required=True)
    for case in p.parse_args().cases:
        r=evaluate(case);print(json.dumps({k:v for k,v in r.items() if k!='input_snapshot'},ensure_ascii=False,indent=2))
