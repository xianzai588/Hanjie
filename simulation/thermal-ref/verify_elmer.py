"""用实际 Elmer 执行解析可解的接口导热、相变和冷质量出生验证。"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

import elmer_reference as ref


def small_case(out, mode, home):
    out.mkdir(parents=True,exist_ok=False)
    meshdir = out/"mesh"; meshdir.mkdir()
    xs = np.array([0.,1.,4.]) if mode=="interface" else np.array([0.,4. if mode=="birth" else 1.])
    nodes = np.array([[x,y,z] for x in xs for y in (0.,1.) for z in (0.,1.)])
    connections = np.array([[4*i+j for j in [1,5,7,3,2,6,8,4]] for i in range(len(xs)-1)])
    materials = np.array([1,2]) if mode=="interface" else np.array([3 if mode=="birth" else 1])
    faces,metadata,bctags = [],[],[]
    for e,conn in enumerate(connections):
        for axis in range(3):
            for sign in (-1,1):
                if axis==0 and ((sign==1 and e<len(connections)-1) or (sign==-1 and e>0)):
                    continue
                area = 1. if axis==0 else xs[e+1]-xs[e]
                faces.append(conn[ref.FACE_NODES[axis,sign]])
                metadata.append([e+1,0,axis+1,sign,area,0.,0.,float(mode=="birth" and axis==2 and sign==1)])
                bctags.append(2 if axis==0 and sign==-1 else 3 if axis==0 and sign==1 else 1)
    faces=np.array(faces); metadata=np.array(metadata)
    nn,ne,nb=len(nodes),len(connections),len(faces)
    np.savetxt(meshdir/"mesh.nodes",np.column_stack([np.arange(1,nn+1),np.full(nn,-1),nodes]),fmt=["%d","%d","%.16g","%.16g","%.16g"])
    np.savetxt(meshdir/"mesh.elements",np.column_stack([np.arange(1,ne+1),materials,np.full(ne,808),connections]),fmt="%d")
    np.savetxt(meshdir/"mesh.boundary",np.column_stack([np.arange(1,nb+1),bctags if mode=="interface" else np.ones(nb),metadata[:,0],np.zeros(nb),np.full(nb,404),faces]),fmt="%d")
    (meshdir/"mesh.header").write_text(f"{nn} {ne} {nb}\n2\n808 {ne}\n404 {nb}\n",encoding="ascii")
    with (out/"reference.dat").open("w",encoding="ascii") as f:
        f.write(f"{nn} {ne} {nb} 1\n")
        f.write(f"{1.e8 if mode=='birth' else 0.} 1 0 4 20 20 20 0 0 1.e6 1.e6 1 1 1.e-10 1\n")
        for mat in (1,2,3):
            k=1.e-3 if mode=="birth" else 3. if mode=="interface" and mat==2 else 1.
            ts,tl,latent=(100.,200.,100.) if mode=="latent" else (2000.,2100.,100.)
            f.write(f"1 {ts} {tl} {latent} 2\n20 1 {k}\n3000 1 {k}\n")
        for e,conn in enumerate(connections):
            f.write(" ".join(map(str,[materials[e],xs[e],xs[e+1]-xs[e],xs[e+1]-xs[e],*conn]))+"\n")
        np.savetxt(f,np.column_stack([metadata,faces]),fmt=["%d"]*4+["%.16g"]*4+["%d"]*4)
        f.write(" ".join(map(str,[1,*connections[0],*([.125]*8)]))+"\n")
    settings=ref.load(ref.SPEC)["solver"].copy()
    # 均匀相变固定点迭代收敛较慢；保持严格容限与失败中止，只增加解析测试预算。
    settings.update(time_step_s=1.e10 if mode=="interface" else 1.,output_interval_steps=1,
                    nonlinear_tolerance=1.e-10,nonlinear_iterations=160 if mode=="latent" else 80)
    sif=ref.sif(settings,1 if mode=="interface" else 3)
    if mode=="interface":
        sif+='''Boundary Condition 2
  Target Boundaries(1) = 2
  Temperature = 20.0
End
Boundary Condition 3
  Target Boundaries(1) = 3
  Temperature = 120.0
End
'''
    elif mode=="latent":
        sif=sif.replace('Volumetric Heat Source = Variable Temperature\n    Real Procedure "ReferenceCallbacks" "BirthSource"','Volumetric Heat Source = Real 100.0')
    (out/"case.sif").write_text(sif,encoding="ascii")
    ref.run(out,home)
    field=np.loadtxt(out/("field-00001.dat" if mode=="interface" else "field-00003.dat"))[:,0]
    history=np.genfromtxt(out/"history.csv",delimiter=",",names=True)
    if mode=="interface":
        exact=np.where(nodes[:,0]<=1,20+50*nodes[:,0],70+50/3*(nodes[:,0]-1))
        error=float(np.max(np.abs(field-exact)))
        return dict(test=mode,maximum_temperature_error_c=error,limit_c=1.e-6,passed=error<1.e-6,
                    definition="Two materials: L1=1, k1=1; L2=3, k2=3; boundary 20/120 C; interface=70 C. Large-dt steady limit.")
    if mode=="latent":
        sensors=np.loadtxt(out/"sensors.dat")
        error=float(np.max(np.abs(sensors[:,1]-[110.,160.,220.])))
        return dict(test=mode,maximum_temperature_error_c=error,limit_c=1.e-5,passed=error<1.e-5,
                    definition="Adiabatic uniform source: rho=cp=1, L=100, phase interval 100..200 C, T0=20; expected 110,160,220 C at 1,2,3 s.")
    relative=float(np.max(np.abs(history["residual_j"])/history["source_j"]))
    volume_error=float(np.max(np.abs(history["deposit_volume_mm3"]-[1.,2.,3.])))
    minimum=float(np.min(history["min_c"]))
    return dict(test=mode,maximum_energy_relative_error=relative,volume_error_mm3=volume_error,minimum_temperature_c=minimum,
                passed=relative<1.e-6 and volume_error<1.e-10 and minimum>=19.999,
                definition="Continuously growing cold mass, constant cp and low conductivity producing nonuniform temperature; independent boundary input must equal enthalpy increase without undershoot.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=ref.HERE/"results/verification")
    parser.add_argument("--elmer-home",type=Path,default=ref.DEFAULT_HOME)
    args=parser.parse_args()
    results=[]
    for mode in ("interface","latent","birth"):
        result=small_case(args.output_dir.resolve()/mode,mode,args.elmer_home)
        print(result,flush=True); results.append(result)
    ref.write_json(args.output_dir/"assessment.json",dict(checks=results,passed=all(x["passed"] for x in results),
                   scope="Component verification only; does not admit the welding thermal history.",
                   callback_sha256=ref.digest(ref.HERE/"ReferenceCallbacks.F90")))
    return 0 if all(x["passed"] for x in results) else 1


if __name__=="__main__":
    raise SystemExit(main())
