"""Independently verify saved P1 melting-depth witnesses by linear programming."""
from pathlib import Path
import argparse,json
import numpy as np
from scipy.optimize import linprog


def audit(case,mesh_path=None):
    case=Path(case)
    rows=np.atleast_2d(np.loadtxt(case/'melting-depth-witness.csv',delimiter=',',skiprows=1))
    mesh_path=Path(mesh_path) if mesh_path is not None else case/'mesh.npz'
    with np.load(mesh_path,allow_pickle=False) as f:x,e,m=f['x'],f['e'],f['material']
    witness_elements=rows[:,3].astype(int)
    np.savez_compressed(case/'melting-depth-witness-geometry.npz',
        vertex_xyz_mm=x[e[witness_elements]],material=m[witness_elements],actual_temperature_witness_rows=rows)
    error=[];deepest={}
    for time,material,segment,element,solidus,saved,*temperatures in rows:
        element=int(element);material=int(material);segment=int(segment)
        if int(m[element])!=material:raise ValueError('witness material differs from mesh')
        T=np.asarray(temperatures);z=x[e[element],2]
        result=linprog(z,A_ub=-T[None,:],b_ub=[-solidus],A_eq=np.ones((1,4)),b_eq=[1.],bounds=(0,None),method='highs')
        if not result.success:raise RuntimeError('independent melting-depth LP failed: '+result.message)
        error.append(abs(result.fun-saved))
        key=f'{material}:{segment}'
        if key not in deepest or result.fun<deepest[key]['minimum_z_mm']:
            deepest[key]=dict(minimum_z_mm=float(result.fun),depth_below_z115_mm=float(115-result.fun),time_s=float(time),element=element,
                barycentric=result.x.tolist(),temperature_C=float(result.x@T))
    summary=json.loads((case/'interface-thermal-history-summary.json').read_text())
    row=dict(mesh_file=str(mesh_path),witness_rows=len(rows),maximum_LP_minimum_z_difference_mm=float(max(error)),deepest=deepest,
        standalone_witness_geometry='melting-depth-witness-geometry.npz',
        independent_witness_replay_pass=bool(max(error)<1e-8),thermal_run_partial=summary['partial'],
        scope='independent constrained affine-temperature minimization on saved actual-temperature tetrahedra; not mesh/time convergence or joint capacity')
    (case/'melting-depth-witness-audit.json').write_text(json.dumps(row,indent=2),encoding='utf8')
    return row


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--mesh',type=Path)
    a=p.parse_args();print(json.dumps(audit(a.case,a.mesh),indent=2))
