"""Run fixed analytic thermoelastic cold baselines with installed Elmer.

These are independent tool baselines, not simulated or measured CI-A1 joints.
No plastic/deposition model is claimed by the linear StressSolve module.
"""
import json
import os
from pathlib import Path
import subprocess
import numpy as np
from mma_literature_profile import ROOT


SOLVER=Path('E:/OpenSource/ElmerFEM-26.1/ElmerFEM-gui-nompi-Windows-AMD64/bin/ElmerSolver.exe')
OUTPUT=ROOT/'simulation/competition-r4/results/elmer-cold-thermoelastic-benchmark-libfix-20261007'


def mesh(folder,length,width,nx,ny,nz,two_materials):
    if (folder/'mesh.nodes').exists():return
    folder.mkdir(parents=True)
    points=[];elements=[];boundaries=[]
    def node(i,j,k):return 1+i+(nx+1)*(j+(ny+1)*k)
    for k in range(nz+1):
        for j in range(ny+1):
            for i in range(nx+1):points.append([i*length/nx,j*width/ny,k*width/nz])
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                q=[node(i,j,k),node(i+1,j,k),node(i+1,j+1,k),node(i,j+1,k),
                   node(i,j,k+1),node(i+1,j,k+1),node(i+1,j+1,k+1),node(i,j+1,k+1)]
                eid=len(elements)+1;body=1+(two_materials and i>=nx//2)
                elements.append([eid,body,808,*q])
                for condition,face,flag in [(1,[0,3,7,4],i==0),(2,[1,2,6,5],i==nx-1),
                                            (3,[0,1,5,4],j==0),(4,[0,1,2,3],k==0)]:
                    if flag:boundaries.append([len(boundaries)+1,condition,eid,0,404,*[q[t] for t in face]])
    (folder/'mesh.nodes').write_text(''.join(f'{i+1} -1 '+ ' '.join(map(str,p))+'\n' for i,p in enumerate(points)))
    for name,rows in [('mesh.elements',elements),('mesh.boundary',boundaries)]:
        (folder/name).write_text(''.join(' '.join(map(str,row))+'\n' for row in rows))
    (folder/'mesh.header').write_text(f'{len(points)} {len(elements)} {len(boundaries)}\n2\n808 {len(elements)}\n404 {len(boundaries)}\n')


def sif(name,temperature,right,materials,restart=None):
    header=f'''Header
  Mesh DB "." "mesh"
End
Simulation
  Coordinate System = Cartesian 3D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Output Intervals = 1
  Output File = "{name}.result"
  Post File = "{name}.vtu"
  Max Output Level = 5
'''
    if restart:header+=f'  Restart File = "{restart}.result"\n'
    header+='End\n'
    for j,(E,nu,alpha,rho,Tref) in enumerate(materials,1):
        header+=f'''Body {j}
  Equation = 1
  Material = {j}
End
Material {j}
  Youngs Modulus = {E}
  Poisson Ratio = {nu}
  Heat Expansion Coefficient = {alpha}
  Reference Temperature = {Tref}
  Density = {rho}
  Heat Conductivity = 0.04
  Heat Capacity = 500
End
'''
    header+='''Equation 1
  Active Solvers(2) = 1 2
End
Solver 1
  Equation = Heat Equation
  Procedure = "HeatSolve" "HeatSolver"
  Variable = Temperature
  Linear System Solver = Direct
  Linear System Direct Method = Umfpack
  Linear System Convergence Tolerance = 1e-12
End
Solver 2
  Equation = Linear Elasticity
  Procedure = "StressSolve" "StressSolver"
  Variable = -dofs 3 Displacement
  Calculate Stresses = True
  Calculate Strains = True
  Linear System Solver = Direct
  Linear System Direct Method = Umfpack
  Linear System Convergence Tolerance = 1e-12
End
'''
    for condition,component in [(1,1),(2,1),(3,2),(4,3)]:
        header+=f'Boundary Condition {condition}\n  Target Boundaries(1) = {condition}\n  Temperature = {temperature}\n'
        if condition!=2 or right is not None:
            header+=f'  Displacement {component} = {right if condition==2 else 0}\n'
        header+='End\n'
    return header


def run():
    if (OUTPUT/'execution.json').exists():raise ValueError('Preserve completed Elmer baseline')
    if not SOLVER.is_file():raise RuntimeError('Installed ElmerSolver unavailable')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    material_Ni=[(205000.,.31,16.7e-6,8890e-9,20.)]
    material_bar=[(170000.,.28,11.4e-6,7200e-9/(1+11.4e-6*20)**3,40.),
                  (205000.,.31,13.3e-6,8890e-9/(1+13.3e-6*20)**3,40.)]
    delta_u=10*(50/170000+50/205000)
    cases=[('Ni-free',10,10,4,4,4,False,material_Ni,[('hot',1000,None,None),('cold',20,None,'hot')]),
           ('QT-Ni-series',100,2,50,2,2,True,material_bar,
            [('hot',40,0,None),('cold',20,0,'hot'),('loaded',20,delta_u,'cold'),('unloaded',20,0,'loaded')])]
    records=[]
    for folder,length,width,nx,ny,nz,two,materials,steps in cases:
        path=OUTPUT/folder;mesh(path/'mesh',length,width,nx,ny,nz,two)
        for name,T,right,restart in steps:
            if (path/'mesh'/(name+'.result')).exists():
                records.append(dict(case=folder,stage=name,returncode=0,previous_actual_state_preserved=True));continue
            (path/(name+'.sif')).write_text(sif(name,T,right,materials,restart),encoding='utf8')
            env=os.environ.copy();env['OMP_NUM_THREADS']='1';env['ELMER_HOME']=str(SOLVER.parent.parent)
            env['ELMER_LIB']=str(SOLVER.parent.parent/'share/elmersolver/lib')
            result=subprocess.run([str(SOLVER),name+'.sif'],cwd=path,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',timeout=120)
            (path/(name+'.log')).write_text(result.stdout,encoding='utf8')
            records.append(dict(case=folder,stage=name,returncode=result.returncode))
            if result.returncode or not (path/'mesh'/(name+'.result')).exists() or '*** Elmer Solver: ALL DONE ***' not in result.stdout:
                raise RuntimeError(f'Elmer {folder}/{name} did not produce its actual solved state; inspect preserved log')
            print(folder,name,'completed',flush=True)
    (OUTPUT/'execution.json').write_text(json.dumps(dict(solver=str(SOLVER),records=records,
        analytic_bar_cold_axial_stress_MPa=20*(50*11.4e-6+50*13.3e-6)/(50/170000+50/205000),
        imposed_additional_elastic_stress_MPa=10,loaded_right_displacement_mm=delta_u,
        sources=['https://www.nic.funet.fi/pub/sci/physics/elmer/doc/ElmerModelsManual.pdf',
                 'https://github.com/ElmerCSC/elmerfem/blob/devel/fem/src/modules/StressSolve.F90'],
        scope='free thermal dilation/recovery and constrained two-material elastic cold residual, then same-reference loading/unloading; no deposited joint or plastic capacity qualification'),indent=2),encoding='utf8')


if __name__=='__main__':run()
