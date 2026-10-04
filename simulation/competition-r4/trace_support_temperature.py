"""Record all thermal increments at the three pad contacts, for fixture drift.

Replays the frozen 40.008 geometry/source. This is a support-temperature
calculation, never a replacement for the cold mechanical verification.
"""
from pathlib import Path
import json,math
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import triu
from threadpoolctl import threadpool_limits
import pypardiso
import run_verified as rv

OUT=Path(__file__).parent/'results'/'bore008-support-thermal-dt0125'
original_mesh=rv.mesh
rows=[]; interpolation=[]
def traced_mesh(*args,**kwargs):
    data=original_mesh(*args,**kwargs);x,e,m=data[:3]
    ids=np.flatnonzero(m==1);centres=x[e[ids]].mean(axis=1);tree=cKDTree(centres)
    for angle in (0,2*np.pi/3,4*np.pi/3):
        point=np.array([30*np.cos(angle),30*np.sin(angle),100.])
        choices=[]
        for count in (16,32):
            distance,neighbours=tree.query(point,k=count)
            scale=max(distance.max(),1)
            Q=np.vstack((np.ones(count),((centres[neighbours]-point)/scale).T))
            weights=Q.T@np.linalg.solve(Q@Q.T,np.array([1.,0,0,0]))
            choices.append((ids[neighbours],weights))
        interpolation.append(choices)
    return data
rv.mesh=traced_mesh
def observer(t,te,*args):
    values=[];errors=[]
    for choices in interpolation:
        a,b=[float(weights@te[indices]) for indices,weights in choices]
        values.append(b);errors.append(abs(a-b))
    rows.append([t,*values,np.ptp(values),max(errors)])
solver=pypardiso.PyPardisoSolver(mtype=2)
def solve(A,b):
    answer=pypardiso.spsolve(triu(A,format='csr'),b,solver=solver)
    if np.linalg.norm(A@answer-b)>.001:raise RuntimeError('thermal linear equilibrium failed')
    return answer
rv.thermal_spsolve=solve;rv.structural_spsolve=solve
rv.DIRECT_SOLVER_NAME='MKL PARDISO symmetric thermal replay';rv.SOLVER_THREADS=1
with threadpool_limits(limits=1):
    rv.run(8,1.5,.125,OUT,imbalance=.05,preheat=20,stop_time=350.,thermal_only=True,
        struct_dt=.25,cold_struct_dt=5.,contact_density=2000.,copper_h=50.,
        source_radius=1.270170592,source_depth=.923760431,weld_h=1.,source_r=74.8,
        seat_path=Path('simulation/competition-r4/geometry/8P-R2-t15.step'),
        thermal_observer=observer,event_dT=12.5,paired=True,unilateral_pads=True,
        material_enthalpy=True,initial_bore_diameter=40.008)
data=np.array(rows)
np.savetxt(OUT/'support-temperature-history.csv',data,delimiter=',',
    header='t_s,pad1_C,pad2_C,pad3_C,spread_C,interpolation_16_vs_32_C',comments='')
result=dict(scope='all thermal increments through350 s, frozen source/geometry; no measured fixture temperature',
    maximum_contact_C=float(data[:,1:4].max()),maximum_simultaneous_spread_C=float(data[:,4].max()),
    maximum_interpolation_difference_C=float(data[:,5].max()),
    all_increment_count=len(data),contact_z_mm=100,pad_radius_mm=30,
    interpolation_weight_L1=[float(np.abs(choices[1][1]).sum()) for choices in interpolation])
(OUT/'support-temperature-verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result),flush=True)
