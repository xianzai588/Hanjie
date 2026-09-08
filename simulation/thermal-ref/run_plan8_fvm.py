"""给既有FVM执行链增加材料账本观测，不修改离散方程。"""
import argparse
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

import run_plan7_fvm as fvm


class PartitionRecorder:
    def __init__(self,out,g,tables,lengths,rho,dt):
        self.out,self.g,self.tables,self.lengths,self.dt=out,g,tables,lengths,dt
        self.rows=[]; self.fields=[]; self.times=[]; self.fractions=[]
        np.savez_compressed(out/"mesh-data.npz",material=g["ids"],index=g["index"],volume=g["volumes"],
                            s_edges=g["s_edges"],n_edges=g["n_edges"],z_edges=g["z_edges"])

    def record(self,t,temperature,fraction,mass,q,loss,born,matrix):
        if t<18.-1.e-8 or t>26.+1.e-8:
            return
        ids=self.g["ids"]; partition=lambda a:np.bincount(ids,weights=a,minlength=4)[1:4]
        h=fvm.core.material_state(temperature,ids,self.tables,self.lengths)[0]
        energy=partition(mass*h)
        i,j=self.g["edge_i"],self.g["edge_j"]
        flows=[]
        for parent in (2,1):
            mask=((ids[i]==3)&(ids[j]==parent))|((ids[j]==3)&(ids[i]==parent))
            ii,jj=i[mask],j[mask]
            value=-np.asarray(matrix[ii,jj]).ravel()*(temperature[ii]-temperature[jj])
            flows.append(float(np.sum(np.where(ids[ii]==3,value,-value))))
        row=[t,*energy,*partition(q*self.dt),*partition(loss*self.dt),*partition(born),*flows,*([0.]*3)]
        if not self.rows:
            row[4:]=[0.]*(len(row)-4)
        self.rows.append(row); self.times.append(t); self.fields.append(temperature.copy()); self.fractions.append(fraction.copy())

    def finish(self):
        header="time_s,H_q235_j,H_qt_j,H_weld_j,source_q235_j,source_qt_j,source_weld_j,loss_q235_j,loss_qt_j,loss_weld_j,birth_q235_j,birth_qt_j,birth_weld_j,weld_to_qt_j,weld_to_q235_j,mix_q235_j,mix_qt_j,mix_weld_j"
        np.savetxt(self.out/"partition.csv",self.rows,delimiter=",",comments="",header=header,fmt="%.15g")
        np.savez_compressed(self.out/"window-fields.npz",times=self.times,temperature=self.fields,fraction=self.fractions)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["dynamic","constant"])
    parser.add_argument("--output-dir",type=Path)
    args=parser.parse_args()
    out=(args.output_dir or Path(__file__).parent/"results/plan8"/f"fvm-{args.mode}").resolve()
    with threadpool_limits(limits=1):
        fvm.run(out,args.mode=="constant",end_time_s=26.,constant_properties=args.mode=="constant",observer_factory=PartitionRecorder)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
