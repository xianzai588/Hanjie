"""Complete-ring final joining: actual thermal FE and conditional eigenstrain response.

Thermal source parameters are declared engineering inputs.  Elastic eigenstrain
responses are response kernels, not calibrated residual-deformation predictions.
Neither calculation proves the first or final fused interface.  No complete
precoat residual-stress/plastic state is imported.  The cold kernels describe
independent, nonzero changes of retained eigenstrain, not state inheritance.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import sys
import yaml
import time
from pathlib import Path
import numpy as np
import gmsh
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import splu, cg
import pyamg
from threadpoolctl import threadpool_limits

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'simulation/competition-r4'))
sys.path.insert(0,str(ROOT/'src'))
from run_candidate_solver import operators
from ni99_local_thermal import tables
from postprocess import section_axis_envelope
from hanjie.simulation.structural_prep import fit_position_diameter
from thermal_inputs import active_exterior_faces,specific_enthalpy,validate_arc_prefix_metadata,tools_may_release,annotate_start_permissions
ORDER=[0,4,2,6,1,5,3,7]
LENGTH=20.
SPEED=1.65
POWER=495.


def validated_process():
    design=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())
    layout=design['weld_layout'];final=design['final_GTAW'];seat=design['geometry']['seat']
    if layout['segment_count']!=8 or layout['pass_count']!=2 or abs(layout['segment_length_mm']-LENGTH)>1e-10 or layout['sequence']!=[j+1 for j in ORDER]:
        raise RuntimeError('current process layout differs from this calculation input: update geometry/schedule before solving')
    if abs(final['travel_speed_mm_s']-SPEED)>1e-10 or abs(final['nominal_net_energy_J_mm']*SPEED-POWER)>1e-10:
        raise RuntimeError('current pWPS power/travel differs from the declared calculation; do not relabel old inputs with a new version')
    if seat['bottom_z_mm']!=100. or seat['thickness_mm']!=15. or seat['nominal_bore_diameter_mm']!=40.:
        raise RuntimeError('current seat geometry differs from this calculation geometry')
    return design


def schedule(idle=18.):
    duration=LENGTH/SPEED
    return [{'pass':p,'segment':j+1,'start_s':(p*8+k)*(duration+idle),
             'end_s':(p*8+k)*(duration+idle)+duration}
            for p in range(2) for k,j in enumerate(ORDER)]


from conforming_mesh import build as build_mesh


def props():
    raw=tables(1300.,.75)
    raw[3]['name']='CI-A1 high-Ni first layer: engineering thermophysical proxy'
    raw[3]['basis']+='; CI-A1 first-layer thermal proxy, not the batch phase diagram or mechanical capacity'
    # Reorder the existing engineering thermal inputs to match the CAD material IDs.
    return [None,raw[1],raw[0],raw[3],raw[4],raw[2]]


def source_definition(root_rise=0.,source_r=75.):
    return dict(radial_mm=source_r,Gaussian_width_mm=1.270170592,Gaussian_depth_mm=.923760431,
      root_z_mm=115.+root_rise,root_target_basis='physical joint root r75/z115 (0.02mm from seat edge); not robot TCP or gun standoff',
      cap_z_mm=117.,cap_height_basis='effective volumetric source estimate; requires macrosection calibration; not a robot TCP instruction',
      qualification='inherited engineering source input; not measured arc shape')


def write_arc_identity(prefix_path,summary,arc_inputs):
    identity=dict(schema='ring-final-accepted-arc-prefix-v1',mesh_cache_key=summary['cache_key'],thermal_result=arc_inputs,
      state_npz_sha256=hashlib.sha256(Path(prefix_path).read_bytes()).hexdigest())
    Path(prefix_path).with_suffix('.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2))


def thermal(level,dt,stop_time=None,root_rise=0.,source_r=75.,linear_solver="pardiso",resume_prefix=None):
    if dt<=0 or (stop_time is not None and stop_time<=0):raise ValueError('time step and stop time must be positive')
    engine=None
    if linear_solver=="pardiso":
        from pardiso_pattern import SymmetricPatternSolver
        engine=SymmetricPatternSolver()
    design=validated_process()
    fixture=design['fixture_feasibility']
    release_policy=dict(minimum_post_arc_hold_s=float(fixture['release_minimum_post_arc_hold_s']),part_max_temperature_exclusive_C=float(fixture['release_part_max_temperature_exclusive_C']),
      source='project/submission-baseline.yaml.fixture_feasibility',evaluation='first accepted cooling step meeting both gates; cooling step sizes5/15/30s')
    if release_policy['minimum_post_arc_hold_s']<0:raise ValueError('post-arc hold cannot be negative')
    d,summary=build_mesh(level);x,e,m,wp=d['x'],d['e'],d['material'],d['weld_pass']
    out=HERE/'results'/(f'{level}-dt{dt:g}'+(f'-stop{stop_time:g}' if stop_time else '')+(f'-root{root_rise:g}-r{source_r:g}' if (root_rise,source_r)!=(1.2,74.8) else ''));out.mkdir(parents=True,exist_ok=True)
    tab=props();nn=len(x);ne=len(e);g,vol,_,_=operators(x,e,False);c=x[e].mean(axis=1)
    rr=np.repeat(e,4,axis=1).ravel();cc=np.tile(e,(1,4)).ravel()
    conduct=np.einsum('eik,ejk,e->eij',g,g,vol)
    faces,owners=d['faces'],d['owners'];fa=.5*np.linalg.norm(np.cross(x[faces[:,1]]-x[faces[:,0]],x[faces[:,2]]-x[faces[:,0]]),axis=1)
    fcent=x[faces].mean(axis=1);fr=np.linalg.norm(fcent[:,:2],axis=1)
    sigma=5.670374419e-14; ambient=20.;T=np.full(nn,ambient);peak=T.copy();observed=np.zeros(ne,bool)
    rho=np.array([0]+[t['nominal_properties_20c']['density_kg_m3'] for t in tab[1:]])[m]*1e-9
    seq=schedule();arcend=seq[-1]['end_s'];rank={j:i for i,j in enumerate(ORDER)}
    theta=np.arctan2(c[:,1],c[:,0]);seg=np.rint(theta/(math.pi/4)).astype(int)%8
    localangle=(theta-seg*math.pi/4+math.pi)%(2*math.pi)-math.pi
    along=74.98*localangle+LENGTH/2
    births=np.array([((int(wp[i])*8+rank[int(seg[i])])*(LENGTH/SPEED+18.)+np.clip(along[i]/SPEED,0,LENGTH/SPEED)) if m[i]==5 else -1. for i in range(ne)])
    def property_at(value,key):
        out=np.zeros_like(value)
        for j,tb in enumerate(tab[1:],1):
            pick=m==j;tr=tb['temperature_dependent'];out[pick]=np.interp(value[pick],tr['temperatures_c'],tr[key])
        return out
    def specific_H(value):
        out=np.zeros_like(value)
        for j,tb in enumerate(tab[1:],1):
            pick=m==j;out[pick]=specific_enthalpy(value[pick],tb)
        return out
    def capacity(value):
        out=property_at(value,'specific_heat_j_kgk')
        for j,tb in enumerate(tab[1:],1):
            fu=tb['fusion_enthalpy'];pick=(m==j)[:,None]&(value>fu['solidus_C'])&(value<fu['liquidus_C'])
            out[pick]+=fu['latent_heat_J_kg']/(fu['liquidus_C']-fu['solidus_C'])
        return out
    def nodal_sum(value):return np.bincount(e.ravel(),weights=(value/4).ravel(),minlength=nn)
    if not np.all(specific_H(np.full((ne,4),ambient))==0.):raise RuntimeError('entering filler enthalpy reference is not zero at20C')
    # Metal-to-copper sink uses the existing ring area, not an unbounded fixed-temperature boundary.
    sys.path.insert(0,str(ROOT/'studies/COMPETITION-DESIGN'))
    import seal_design
    seal=seal_design.evaluate();ct=22.;ccap=seal['copper_heat_capacity_J_K'];water=seal['water_lumped_design_W_K']
    copper_mask=(abs(fr-75)<.5)&(fcent[:,2]>=seal['copper_bottom_z_mm'])&(fcent[:,2]<=seal['copper_top_z_mm'])
    # Convection contact coefficient is a declared 50 W/m2K engineering input.
    t=0.;energy=0.;losses=0.;history=[];starts=[dict(**seq[0],second_layer_current_max_C=ambient,interpass_100C=True)];saved={};startclock=time.time();balance_max=0.;maxiter=0
    continuation=None;tools_present=True;tool_release=None
    if resume_prefix is not None:
        prefix=np.load(resume_prefix)
        identity=json.loads(Path(resume_prefix).with_suffix('.json').read_text())
        previous=identity['thermal_result']
        validate_arc_prefix_metadata(identity,dict(mesh_cache_key=summary['cache_key'],process_version=validated_process()['version'],arc_dt_s=dt,
          declared_source=source_definition(root_rise,source_r),material_inputs=tab[1:]),hashlib.sha256(Path(resume_prefix).read_bytes()).hexdigest())
        t=float(prefix['time_s']);energy=float(prefix['input_J']);losses=float(prefix['external_loss_J'])
        if abs(t-arcend)>1e-7 or abs(energy-96000)>1e-6 or len(previous['start_records'])!=16:
            raise RuntimeError('continuation requires actual complete16-segment arc prefix with96kJ and16 start records')
        T=prefix['temperature'].copy();peak=prefix['peak_temperature'].copy();ct=float(prefix['copper_temperature'])
        history=prefix['history'].tolist();starts=previous['start_records'];saved={k:prefix[k].copy() for k in ('first_root','end_arc')}
        if abs(history[-1][0]-t)>1e-8 or abs(history[-1][5]-energy)>1e-7 or abs(history[-1][6]-losses)>1e-7:
            raise RuntimeError('accepted arc checkpoint history and state ledger disagree')
        balance_max=max(abs(r[7]) for r in history);maxiter=max(r[9] for r in history)
        continuation=dict(source=str(Path(resume_prefix).resolve().relative_to(ROOT)),sha256=hashlib.sha256(Path(resume_prefix).read_bytes()).hexdigest(),time_s=t,input_J=energy,
          purpose='retain actual accepted16-arc state; recompute cooling only with>=120s post-arc AND max<55C tooling exit boundary',prefix_original_solver=previous['linear_solver'])
    precon=None;factor_age=0
    events=np.unique([0.,arcend,*[r['start_s'] for r in seq],*[r['end_s'] for r in seq]])
    while t<arcend+12000:
        if tools_present and tools_may_release(t,arcend,float(T.max()),release_policy):
            tools_present=False;tool_release=dict(time_s=t,part_max_C=float(T.max()),copper_C=ct,time_after_final_arc_s=t-arcend,criterion='declared minimum post-arc hold AND whole-part max below release threshold; product exits copper fixture')
        source_on=any(r['start_s']-1e-8<=t<r['end_s']-1e-8 for r in seq)
        step=dt if source_on else (min(4.,4.*dt) if t<arcend else (5. if T.max()>100 else 15. if T.max()>55 else 30.))
        nextevent=events[events>t+1e-8]
        if len(nextevent):step=min(step,float(nextevent[0]-t))
        if stop_time is not None:step=min(step,stop_time-t)
        if step<=1e-9:break
        nt=t+step;mid=t+step/2;active=(m!=5)|(births<=nt)
        old_active=(m!=5)|(births<=t)
        occupied=np.unique(e[active]);inactive=np.setdiff1d(np.arange(nn),occupied)
        expose=active_exterior_faces(active,owners)
        sa=np.bincount(faces[expose].ravel(),weights=np.repeat(fa[expose]/3,3),minlength=nn)
        ca=np.bincount(faces[expose&copper_mask].ravel(),weights=np.repeat(fa[expose&copper_mask]/3,3),minlength=nn)
        if ca.sum()>0:ca*=seal['copper_effective_area_mm2']/ca.sum()
        if not tools_present:ca[:]=0.
        contact=50e-6*ca
        qelem=np.zeros(ne);record=next((r for r in seq if r['start_s']-1e-8<=mid<r['end_s']-1e-8),None)
        if record:
            j=record['segment']-1;p=record['pass'];progress=(mid-record['start_s'])*SPEED
            a=j*math.pi/4+(progress-LENGTH/2)/74.98
            source=np.array([source_r*math.cos(a),source_r*math.sin(a),115.+root_rise if p==0 else 117.])
            dd=c-source;gauss=np.exp(-((dd[:,0]**2+dd[:,1]**2)/1.270170592**2+(dd[:,2]/.923760431)**2))*vol*active
            if gauss.sum()<=0:raise RuntimeError('source outside occupied metal')
            qelem=POWER*gauss/gauss.sum()
        qnodal=nodal_sum(np.repeat(qelem[:,None],4,axis=1))
        oldH=nodal_sum(specific_H(T[e])*rho[:,None]*vol[:,None]*old_active[:,None])
        guess=T.copy();ctguess=ct
        converged=False
        for it in range(35):
            vals=guess[e];H=nodal_sum(specific_H(vals)*rho[:,None]*vol[:,None]*active[:,None])
            C=nodal_sum(capacity(vals)*rho[:,None]*vol[:,None]*active[:,None])
            k=property_at(vals.mean(axis=1),'thermal_conductivity_w_mk')*.001*active
            K=coo_matrix((conduct.ravel()*np.repeat(k,16),(rr,cc)),shape=(nn,nn)).tocsr()
            radiation=.7*sigma*sa*((guess+273.15)**4-293.15**4)
            conv=15e-6*sa*(guess-ambient)
            ctguess=(ccap/step*ct+water*22.+contact@guess)/(ccap/step+water+contact.sum())
            loss=conv+radiation+contact*(guess-ctguess)
            residual=(H-oldH)/step+K@guess+loss-qnodal
            norm=float(np.linalg.norm(residual[occupied]))
            if norm<1e-7:converged=True;break
            tangent=K+diags(C/step+15e-6*sa+4*.7*sigma*sa*(guess+273.15)**3+contact)
            # The scalar copper temperature is analytically eliminated.
            A=(tangent+diags(np.isin(np.arange(nn),inactive).astype(float))).tocsr()
            if engine is not None:
                fullcorrection=engine(A,-residual)
            else:
                if precon is None or factor_age>=20:
                    ml=pyamg.smoothed_aggregation_solver(A,B=np.ones((nn,1)),symmetry='symmetric',max_coarse=250,max_levels=10)
                    precon=ml.aspreconditioner();factor_age=0
                fullcorrection,info=cg(A,-residual,M=precon,rtol=1e-10,atol=1e-9,maxiter=500)
                if info:fullcorrection=splu(A.tocsc()).solve(-residual);precon=None
            if np.linalg.norm(A@fullcorrection+residual)>1e-7:raise RuntimeError('thermal linear residual exceeds1e-7W')
            correction=fullcorrection[occupied];factor_age+=1
            # A monotone temperature line search prevents crossing T=-273.15,
            # without clipping or suppressing a physically hot state.
            accepted=False
            for power in range(14):
                scale=.5**power
                candidate=guess.copy();candidate[occupied]+=scale*correction
                if candidate[occupied].min()<0:continue
                hc=nodal_sum(specific_H(candidate[e])*rho[:,None]*vol[:,None]*active[:,None])
                kc=property_at(candidate[e].mean(axis=1),'thermal_conductivity_w_mk')*.001*active
                km=coo_matrix((conduct.ravel()*np.repeat(kc,16),(rr,cc)),shape=(nn,nn)).tocsr()
                tc=(ccap/step*ct+water*22.+contact@candidate)/(ccap/step+water+contact.sum())
                lc=15e-6*sa*(candidate-ambient)+.7*sigma*sa*((candidate+273.15)**4-293.15**4)+contact*(candidate-tc)
                rc=(hc-oldH)/step+km@candidate+lc-qnodal
                if np.linalg.norm(rc[occupied])<norm:
                    guess=candidate;accepted=True;break
            if not accepted:raise RuntimeError(f'energy Newton line search stagnation at{nt:g}s residual{norm:g}W')
        if not converged:raise RuntimeError(f'energy Newton failed at {nt:g}s residual {norm:g}W')
        T=guess;ct=ctguess;peak=np.maximum(peak,T);t=nt
        increment=float((H-oldH).sum());inputJ=float(qnodal.sum()*step);lossJ=float(loss.sum()*step)
        balance=increment+lossJ-inputJ;balance_max=max(balance_max,abs(balance));energy+=inputJ;losses+=lossJ;maxiter=max(maxiter,it)
        if T[occupied].max()>3000:raise RuntimeError(f'vapour-free model exceeded at {t}s: {T.max()}C')
        history.append([t,step,float(T.max()),float(T.min()),ct,energy,losses,balance,norm,it])
        for startrecord in seq:
            if abs(t-startrecord['start_s'])<1e-8:
                j=startrecord['segment']-1
                surface=(m==4)&(seg==j)
                localmax=float(T[np.unique(e[surface])].max())
                starts.append(dict(**startrecord,second_layer_current_max_C=localmax,interpass_100C=localmax<=100))
        if record and (record['pass'],record['segment'])==(0,1) and t>=record['end_s']-1e-8:saved.setdefault('first_root',T.copy())
        if abs(t-arcend)<1e-8:saved['end_arc']=T.copy()
        if any(abs(t-r['end_s'])<1e-8 for r in seq) or (t>arcend and len(history)%10==0):
            np.savez_compressed(out/'accepted-thermal-checkpoint.npz',temperature=T,peak_temperature=peak,copper_temperature=ct,time_s=t,input_J=energy,external_loss_J=losses,history=np.asarray(history),**saved)
        if abs(t-arcend)<1e-8:
            np.savez_compressed(out/'end-arc-prefix-checkpoint.npz',temperature=T,peak_temperature=peak,copper_temperature=ct,time_s=t,input_J=energy,external_loss_J=losses,history=np.asarray(history),**saved)
            write_arc_identity(out/'end-arc-prefix-checkpoint.npz',summary,dict(process_version=validated_process()['version'],arc_dt_s=dt,
              material_inputs=tab[1:],declared_source=source_definition(root_rise,source_r),start_records=starts,linear_solver=linear_solver))
        if len(history)%10==0:
            print('thermal',level,dt,round(t,2),round(T.max(),2),round(time.time()-startclock,1),flush=True)
            (out/'progress.json').write_text(json.dumps(dict(t_s=t,arc_end_s=arcend,max_C=float(T.max()),elapsed_s=time.time()-startclock)))
        if t>arcend and not tools_present and T.max()<21.:break
        if stop_time is not None and t>=stop_time-1e-8:break
    np.savetxt(out/'thermal-history.csv',history,delimiter=',',header='t_s,dt_s,part_max_C,part_min_C,copper_C,input_J,external_loss_J,step_balance_J,residual_W,newton_iterations',comments='')
    np.savez_compressed(out/'thermal-fields.npz',temperature=T,peak_temperature=peak,**saved)
    bore=abs(np.linalg.norm(x[:,:2],axis=1)-20)<1e-5
    starts=annotate_start_permissions(starts,design['final_GTAW'])
    result=dict(model='3D four-node tetrahedral thermal enthalpy FE; nominal retained layers and source births; no melt transport',mesh=summary,
      material_inputs=tab[1:],arc_schedule=seq,travel_mm_s=SPEED,actual_segment_mm=LENGTH,net_W=POWER,net_energy_J_mm=300.,
      declared_source=source_definition(root_rise,source_r),
      source_domain='all occupied material volumes (QT,first-layer,second-layer,NiFe,Q235); Gaussian normalized over these volumes',linear_solver=linear_solver,source_energy_J=energy,nominal_ledger_J=96000.,arc_dt_s=dt,idle_dt_s=min(4.,4.*dt),cooling_dt_s=[5.,15.,30.],end_s=t,max_C=float(peak.max()),bore_peak_C=float(peak[bore].max()),material_peak_C={str(j):float(peak[np.unique(e[m==j])].max()) for j in range(1,6)},final_max_C=float(T.max()),
      tooling_exit=tool_release,tooling_release_policy=release_policy,cooling_boundary='air20C h15W/m2K/emissivity0.7 throughout; finite water-cooled copper contact until both declared post-arc hold and temperature gates pass, then product leaves tooling',accepted_arc_continuation=continuation,
      copper_peak_C=max(r[4] for r in history),max_step_balance_J=balance_max,max_Newton_iterations=maxiter,
      start_records=starts,interpass_limits_pass=all(r['interpass_100C'] for r in starts),elapsed_s=time.time()-startclock,
      start_temperature_permissions_pass=all(r['temperature_permission_pass'] for r in starts),start_permission_scope='conservative first-pass start window15..35C; subsequent pass15..100C; interpass_100C retained separately',
      elapsed_scope='continuation wall time only; original16-arc calculation is identified separately' if continuation else 'whole calculation wall time',current_evidence_usable=True,
      complete_final_thermal_cycle=bool(t>=arcend and not tools_present and T.max()<21.),stop_time_s=stop_time,precoat_residual_state="not imported or solved by thermal model; independent mechanical input required",mechanical_state_computed=False,full_manufacturing_chain_passed=False,
      process_version=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())['version'],planned_path_mm=320.,executed_path_mm=energy/300.,actual_path_320mm=bool(abs(energy-96000.)<1e-6),
      scope='actual final-weld thermal design calculation on retained nominal precoat geometry; precoat stress history and continuous fused interfaces remain separate inputs')
    (out/'thermal-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--level',choices=['coarse','medium'],default='coarse');ap.add_argument('--dt',type=float,default=.5);ap.add_argument('--mesh-only',action='store_true');ap.add_argument('--stop-time',type=float);ap.add_argument('--root-rise',type=float,default=0.);ap.add_argument('--source-r',type=float,default=75.);ap.add_argument('--linear-solver',choices=['pardiso','amg'],default='pardiso');ap.add_argument('--resume-arc-prefix',type=Path)
    a=ap.parse_args()
    with threadpool_limits(limits=2):
        if a.mesh_only:build_mesh(a.level)
        else:thermal(a.level,a.dt,a.stop_time,a.root_rise,a.source_r,a.linear_solver,a.resume_arc_prefix)
if __name__=='__main__':main()
