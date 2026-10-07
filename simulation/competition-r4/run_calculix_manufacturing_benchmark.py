"""One native history: substrate plasticity, deposition, cold cutting and load release.

Fixed two-layer tool benchmark, not the competition joint. Uses the mature
solver's own state variables and model-change features without a custom UMAT.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import numpy as np
from mma_literature_profile import ROOT

SOLVER=Path('E:/OpenSource/CalculiX-2.23/calculix_2.23_4win/ccx_static.exe')
OUT=ROOT/'simulation/competition-r4/results/calculix-plastic-deposition-cut-benchmark-restartfix-20261007'


def make_input():
    nx,ny,nz=10,2,4
    def node(i,j,k):return 1+i+(nx+1)*(j+(ny+1)*k)
    points=np.array([[i,j,k/2] for k in range(nz+1) for j in range(ny+1) for i in range(nx+1)],float)
    elements=[]; qt=[];ni=[];cut=[]
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                nodes=[node(i,j,k),node(i+1,j,k),node(i+1,j+1,k),node(i,j+1,k),node(i,j,k+1),node(i+1,j,k+1),node(i+1,j+1,k+1),node(i,j+1,k+1)]
                eid=len(elements)+1;elements.append([eid,*nodes])
                (qt if k<2 else ni).append(eid)
                if k==3:cut.append(eid)
    groups={'ALLN':list(range(1,len(points)+1)),
            'LEFT':(np.flatnonzero(points[:,0]==0)+1).tolist(),
            'RIGHT':(np.flatnonzero(points[:,0]==10)+1).tolist(),
            'YSYM':(np.flatnonzero(points[:,1]==0)+1).tolist(),
            'ZSYM':(np.flatnonzero(points[:,2]==0)+1).tolist()}
    text='*HEADING\nNative plastic deposition/cold cut history benchmark, mm N MPa C\n*NODE,NSET=ALLN\n'
    text+=''.join(f'{i+1},'+','.join(map(str,p))+'\n' for i,p in enumerate(points))
    text+='*ELEMENT,TYPE=C3D8,ELSET=ALLE\n'+''.join(','.join(map(str,q))+'\n' for q in elements)
    for name,ids in [('QT',qt),('NI',ni),('CUT',cut)]:
        text+=f'*ELSET,ELSET={name}\n'+''.join(','.join(map(str,ids[k:k+16]))+'\n' for k in range(0,len(ids),16))
    for name,ids in groups.items():
        if name=='ALLN':continue
        text+=f'*NSET,NSET={name}\n'+''.join(','.join(map(str,ids[k:k+16]))+'\n' for k in range(0,len(ids),16))
    text+='''*MATERIAL,NAME=QT_REF
*ELASTIC
170000,.28
*PLASTIC
310,0
310,.1
*EXPANSION,ZERO=20
11.4e-6
*MATERIAL,NAME=NI_REF
*ELASTIC
205000,.31
*PLASTIC
73.75,0
105,.01
*EXPANSION,ZERO=20
13.3e-6
*SOLID SECTION,ELSET=QT,MATERIAL=QT_REF
*SOLID SECTION,ELSET=NI,MATERIAL=NI_REF
*INITIAL CONDITIONS,TYPE=TEMPERATURE
ALLN,20
'''
    # No thermal source or manufacturing pass is assigned by this tool benchmark.
    stages=[('substrate_plastic',20,.03,'*MODEL CHANGE,TYPE=ELEMENT,REMOVE\nNI\n'),
            ('substrate_unload',20,0,''),
            ('substrate_reheat',200,0,''),
            ('deposit_coherent',200,0,'*MODEL CHANGE,TYPE=ELEMENT,ADD=STRAIN FREE\nNI\n'),
            ('cold',20,0,''),
            ('cut',20,0,'*MODEL CHANGE,TYPE=ELEMENT,REMOVE\nCUT\n'),
            ('loaded',20,-.0002,''),
            ('unloaded',20,0,'')]
    for label,T,right,change in stages:
        text+=f'** {label}\n*STEP,NLGEOM,INC=100\n*STATIC,SOLVER=SPOOLES\n.1,1,1e-6,.25\n'+change
        text+=f'*BOUNDARY\nLEFT,1,1,0\nRIGHT,1,1,{right}\nYSYM,2,2,0\nZSYM,3,3,0\n*TEMPERATURE\nALLN,{T}\n'
        text+='*NODE PRINT,NSET=ALLN,FREQUENCY=99999\nU,RF\n*EL PRINT,ELSET=ALLE,FREQUENCY=99999\nS,PEEQ,ME\n*NODE FILE,FREQUENCY=99999\nU\n*EL FILE,FREQUENCY=99999\nS,PEEQ\n*RESTART,WRITE\n*END STEP\n'
    return text,points,np.array(elements,dtype=int),stages


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'execution.json').exists():raise ValueError('Preserve executed benchmark')
    text,points,elements,stages=make_input()
    (OUT/'benchmark.inp').write_text(text,encoding='ascii')
    np.savez_compressed(OUT/'mesh.npz',points=points,elements=elements)
    env=os.environ.copy();env['OMP_NUM_THREADS']='1';env['CCX_NPROC_RESULTS']='1';env['CCX_NPROC_STIFFNESS']='1'
    start=time.monotonic()
    result=subprocess.run([str(SOLVER),'-i','benchmark'],cwd=OUT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',timeout=120)
    (OUT/'solver.log').write_text(result.stdout,encoding='utf8')
    record=dict(solver=str(SOLVER),runtime_s=time.monotonic()-start,returncode=result.returncode,stages=[s[0] for s in stages],
                scope='native history functionality; constant material references in a fixed benchmark, not actual CI-A1 geometry, thermal history or capacity',
                sources=['https://www.dhondt.de/','CalculiX 2.23 official manual: *PLASTIC, *MODEL CHANGE, *RESTART'])
    (OUT/'execution.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(json.dumps(record,indent=2))
    if result.returncode or '*ERROR' in result.stdout or 'Job finished' not in result.stdout or not (OUT/'benchmark.rout').exists():
        raise RuntimeError('Native benchmark failed; preserve actual log and state')


if __name__=='__main__':main()
