"""Fixed sequential thermal/mechanical deck for the actual one-wing heat path.

Native whole-element solidification clusters replace microscopic cut slivers.
This is a concrete engineering representation candidate. Cold volume/reference
and retained-state qualification are required before its use for machining.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import time
import numpy as np
import yaml
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from mma_literature_profile import ROOT
from run_calculix_manufacturing_benchmark import SOLVER


def rows(ids):
    return ''.join(','.join(map(str,ids[j:j+16]))+'\n' for j in range(0,len(ids),16))


def history(folder):
    manifest=json.loads((folder/'nodal-thermal-history/manifest.json').read_text())
    for chunk in manifest['chunks']:
        with np.load(folder/'nodal-thermal-history'/chunk['file']) as f:
            for i,t in enumerate(f['time_s']):
                yield float(t),f['temperature_C'][i].copy(),f['deposit_element_indices'].copy(),f['deposit_fraction'][i].copy()


def build(out,stop,linear_geometry=False,qt_hardening=False,native_gauss_phase=False):
    source=ROOT/'simulation/competition-r4/results/mma-first-end80-r12-phase-front-dt0125-20261007'
    furnace=ROOT/'simulation/competition-r4/results/mma-one-wing-furnace-phase-front-20261007'
    inp=json.loads((source/'input.json').read_text());ref=yaml.safe_load((ROOT/'project/precoat-mechanical-reference.yaml').read_text(encoding='utf8'))
    hardening=yaml.safe_load((ROOT/'project/precoat-native-hardening-reference.yaml').read_text(encoding='utf8')) if qt_hardening else None
    f=np.load(source/'thermal-fields.npz');x,e,m,V=f['x'],f['e'],f['material'],f['volume_mm3']
    # Face adjacency is used only to schedule already coherent native clusters.
    faces=np.sort(np.vstack([e[:,q] for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
    owners=np.tile(np.arange(len(e)),4)
    uniq,first,inv,count=np.unique(faces,axis=0,return_index=True,return_inverse=True,return_counts=True)
    last=np.zeros(len(count),int);np.maximum.at(last,inv,np.arange(len(faces)))
    pair=np.c_[owners[first],owners[last]];shared=count==2
    edges=pair[shared];edge_faces=uniq[shared]
    inter=m[edges[:,0]]!=m[edges[:,1]]
    fused=np.zeros(len(edges),bool);fused[~inter]=True
    Ts=np.array([r['fusion_enthalpy']['solidus_C'] for r in inp['materials']])[m]
    Tl=np.array([r['fusion_enthalpy']['liquidus_C'] for r in inp['materials']])[m]
    threshold=np.max(Tl[edges],axis=1)
    initial=float(inp['cold_start_C']);previous=np.full(len(x),initial)
    active=m==1;last_t=0.;records=[];selected=[]
    for folder in [source,furnace]:
        for t,T,ids,frac in history(folder):
            fused|=(T[edge_faces].min(axis=1)>=threshold)
            if stop is not None and t>stop+1e-8:break
            occupation=np.ones(len(e));occupation[ids]=frac
            # Native C3D4 has one constitutive point at the barycentre. A
            # corner maximum removes still-coherent integration-point material
            # and can create an artificial one-tetrahedron tip. This option is
            # a fixed engineering quadrature representation, not temperature
            # clipping or a statement that every point of the cell is solid.
            cell_T=T[e].mean(axis=1) if native_gauss_phase else T[e].max(axis=1)
            eligible=(cell_T<=Ts)&(occupation>=1-1e-10)
            good_edge=eligible[edges].all(axis=1)&fused
            q=edges[good_edge]
            graph=coo_matrix((np.ones(2*len(q)),(np.r_[q[:,0],q[:,1]],np.r_[q[:,1],q[:,0]])),shape=(len(e),len(e))).tocsr()
            _,labels=connected_components(graph,directed=False)
            reachable=np.isin(labels,np.unique(labels[eligible&(m==1)]))
            new=eligible&((m==1)|reachable)
            # A shared-node deposited element is withheld while any incident
            # physical interface face has not yet met the whole-face gate.
            gate=~fused | ~(T[edge_faces].max(axis=1)<=np.min(Ts[edges],axis=1))
            forbidden_nodes=np.unique(edge_faces[inter&gate])
            new[(m!=1)&np.isin(e,forbidden_nodes).any(axis=1)]=False
            # Recheck after the interface gate: withholding boundary clusters
            # must not leave an unsupported interior deposit island active.
            q=edges[new[edges].all(axis=1)&fused]
            graph=coo_matrix((np.ones(2*len(q)),(np.r_[q[:,0],q[:,1]],np.r_[q[:,1],q[:,0]])),shape=(len(e),len(e))).tocsr()
            _,labels=connected_components(graph,directed=False)
            new[(m!=1)&~np.isin(labels,np.unique(labels[new&(m==1)]))]=False
            changed=np.any(new!=active)
            final=(stop is not None and abs(t-stop)<1e-8)
            if changed or np.max(abs(T-previous))>=12.5 or (folder==source and t-last_t>=60) or final:
                removed=np.flatnonzero(active&~new)+1;added=np.flatnonzero(~active&new)+1
                selected.append((t,T.copy(),removed,added,new.copy()))
                records.append([t,len(removed),len(added),float(V[new&(m==1)].sum()),float(V[new&(m==3)].sum()),float(V[eligible&(m==3)&~new].sum())])
                active=new.copy();previous=T.copy();last_t=t
                if len(selected)%25==0:print('deck',len(selected),round(t,3),flush=True)
        if stop is not None and last_t>=stop-1e-8:break
    # Include the actual last saved cold temperature, independent of selection.
    if stop is None:
        t,T,ids,frac=list(history(furnace))[-1]
        if t!=last_t:
            selected.append((t,T,np.array([],int),np.flatnonzero(~active)+1,np.ones(len(e),bool)))
            records.append([t,0,int((~active).sum()),float(V[m==1].sum()),float(V[m==3].sum()),0])
    out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out/'mesh.npz',x=x,e=e,material=m,volume_mm3=V)
    with (out/'cluster-events.csv').open('w',newline='') as q:
        writer=csv.writer(q);writer.writerow(['actual_time_s','removed_elements','added_elements','coherent_QT_volume_mm3','connected_Ni_volume_mm3','withheld_Ni_volume_mm3']);writer.writerows(records)
    with (out/'onewing.inp').open('w',encoding='ascii') as q:
        q.write('*HEADING\nActual CI-A1 one-wing sequential heat path; native solid clusters, mm N MPa C\n*NODE,NSET=ALLN\n')
        q.writelines(f'{i+1},'+','.join(f'{v:.12g}' for v in p)+'\n' for i,p in enumerate(x))
        q.write('*ELEMENT,TYPE=C3D4,ELSET=ALLE\n');q.writelines(f'{i+1},'+','.join(map(str,p+1))+'\n' for i,p in enumerate(e))
        for mid,name in [(1,'QT'),(3,'NI')]:q.write(f'*ELSET,ELSET={name}\n'+rows(np.flatnonzero(m==mid)+1))
        q.write('*MATERIAL,NAME=QT_REF\n*ELASTIC\n')
        qt=ref['QT_reference'];ni=ref['high_Ni_reference']
        for T,E in zip(qt['temperatures_C'],qt['E_GPa']):q.write(f'{1000*E},{qt["poisson"]},{T}\n')
        q.write('*PLASTIC\n')
        for T,Y in zip(qt['temperatures_C'],qt['source_yield_MPa']):
            Y*=qt['yield_grade_scale']
            if hardening:
                s=hardening['source']
                for p in hardening['tabulation']['plastic_strain_points']:
                    stress=Y*(1+s['tensile_B_MPa']/s['tensile_A_MPa']*p**s['tensile_n'])
                    q.write(f'{stress:.12g},{p:.12g},{T}\n')
            else:q.write(f'{Y:.12g},0,{T}\n{Y:.12g},.1,{T}\n')
        q.write('*EXPANSION,ZERO=20\n')
        for T,a in zip(qt['temperatures_C'],qt['mean_alpha_20C_per_K']):q.write(f'{a},{T}\n')
        q.write('*MATERIAL,NAME=NI_REF\n*ELASTIC\n')
        for T in sorted(set(ni['temperatures_C']+[1000,1100,1200,1340])):
            E=np.interp(T,ni['temperatures_C'],ni['E_GPa'])
            if T>900:E=134-.06*(T-900)
            q.write(f'{1000*E},{ni["poisson"]},{T}\n')
        q.write('*PLASTIC\n')
        for T in sorted(set(ni['yield_temperatures_C']+[700,800,900,1000,1100,1200,1340])):
            scale=1 if T<=600 else (1400-T)/800
            H=3125*scale;Y=(np.interp(T,ni['yield_temperatures_C'],ni['yield_MPa']) if T<=600 else 40*scale)-.002*H
            q.write(f'{Y:.12g},0,{T}\n{Y+.01*H:.12g},.01,{T}\n')
        q.write('*EXPANSION,ZERO=20\n')
        for T in sorted(set(ni['temperatures_C']+[1000,1100,1200,1340])):
            a=np.interp(T,ni['temperatures_C'],ni['mean_alpha_20C_per_K'])
            if T>900:a=16.5e-6+2e-9*(T-900)
            q.write(f'{a:.12g},{T}\n')
        q.write('*SOLID SECTION,ELSET=QT,MATERIAL=QT_REF\n*SOLID SECTION,ELSET=NI,MATERIAL=NI_REF\n*INITIAL CONDITIONS,TYPE=TEMPERATURE\nALLN,20\n')
        # Only rigid motions are removed; no manufacturing restraint is added.
        anchors=[197,1414,1400]
        bc=f'*BOUNDARY\n{anchors[0]},1,3,0\n{anchors[1]},2,3,0\n{anchors[2]},3,3,0\n'
        regime=',NLGEOM=NO' if linear_geometry else ',NLGEOM'
        q.write(f'*STEP{regime},INC=100\n*STATIC,SOLVER=SPOOLES\n.25,1,1e-6,.5\n*MODEL CHANGE,TYPE=ELEMENT,REMOVE\nNI\n'+bc+f'*TEMPERATURE\nALLN,{initial}\n*END STEP\n')
        for i,(t,T,removed,added,active) in enumerate(selected):
            regime=',NLGEOM=NO' if linear_geometry else ',NLGEOM'
            q.write(f'** Actual thermal time {t:.12g} s\n*STEP{regime},INC=100\n*STATIC,SOLVER=SPOOLES\n.25,1,1e-6,.5\n')
            if len(removed):q.write('*MODEL CHANGE,TYPE=ELEMENT,REMOVE\n'+rows(removed))
            if len(added):
                mode='WITH STRAIN' if native_gauss_phase else 'STRAIN FREE'
                q.write(f'*MODEL CHANGE,TYPE=ELEMENT,ADD={mode}\n'+rows(added))
            q.write(bc+'*TEMPERATURE\n');q.writelines(f'{j+1},{v:.12g}\n' for j,v in enumerate(T))
            if i==len(selected)-1:
                q.write('*NODE PRINT,NSET=ALLN,FREQUENCY=99999\nU,RF\n*EL PRINT,ELSET=ALLE,FREQUENCY=99999\nS,PEEQ,ME\n*NODE FILE,FREQUENCY=99999\nU\n*EL FILE,FREQUENCY=99999\nS,PEEQ\n*RESTART,WRITE\n')
            elif i==0:q.write('*RESTART,WRITE,FREQUENCY=25\n')
            q.write('*END STEP\n')
    metadata=dict(source=str(source),furnace=str(furnace),last_time_s=selected[-1][0],selected_steps=len(selected),
                  strain_regime='native small strain plasticity, geometric applicability requires cold audit' if linear_geometry else 'native large strain plasticity',
                  material_reference=ref,QT_hardening_reference=hardening, engineering_representation='native whole-element coherent clusters; partial birth/solid caps are withheld; actual interface whole-face melting and cooling gate retained; no liquid stiffness or early bond',
                  reference_policy=('native ADD=WITH STRAIN keeps the original cold material reference and all previous plastic history; new Ni has a prescribed cold material shape, not an independently zero-stress hot birth. Activation closure stress and cold volume require explicit audit; this is not a calibrated molten-shape transport model' if native_gauss_phase else 'native stress-free new coherent addition retains previous integration-point plastic state; cold mass/specific-volume qualification remains mandatory'),
                  phase_sampling='native one-point C3D4 barycentre; whole-face physical fusion gate retained' if native_gauss_phase else 'all-corner solid phase',
                  actual_carried_Ni_mass_g=float(V[m==3].sum()*8.89e-3),
                  actual_first_layer_joint_passed=False, cold_geometry_qualified=False,full_manufacturing_chain_passed=False,
                  sources=['https://www.dhondt.de/','https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/add_ded/add_ded_method_abstract.html'])
    (out/'input.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps({k:metadata[k] for k in ['last_time_s','selected_steps','actual_carried_Ni_mass_g']},indent=2),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--stop-time',type=float);p.add_argument('--linear-geometry',action='store_true');p.add_argument('--qt-source-hardening',action='store_true');p.add_argument('--native-gauss-phase',action='store_true');a=p.parse_args()
    out=ROOT/a.output
    if (out/'input.json').exists():raise ValueError('Preserve existing native manufacturing run')
    build(out,a.stop_time,a.linear_geometry,a.qt_source_hardening,a.native_gauss_phase)
    env=os.environ.copy();env['OMP_NUM_THREADS']='4';env['CCX_NPROC_RESULTS']='4';env['CCX_NPROC_STIFFNESS']='4'
    start=time.monotonic()
    with (out/'solver.log').open('w',encoding='utf8') as log:
        r=subprocess.run([str(SOLVER),'-i','onewing'],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
    log=(out/'solver.log').read_text();done=r.returncode==0 and '*ERROR' not in log and 'Job finished' in log and (out/'onewing.rout').exists()
    (out/'execution.json').write_text(json.dumps(dict(returncode=r.returncode,runtime_s=time.monotonic()-start,native_solver_completed=done,cold_geometry_qualified=False,full_manufacturing_chain_passed=False),indent=2),encoding='utf8')
    if not done:raise RuntimeError('Actual native manufacture run failed; preserve log')


if __name__=='__main__':main()
