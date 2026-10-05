"""Compare the actual preconnection gauge schedule using each saved mesh."""
from pathlib import Path
import json
import numpy as np

OUT=Path(__file__).parent/'results'


def evaluate(case):
    folder=OUT/case;inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    with np.load(folder/'mesh.npz') as f:x,e,m,links=(f[k] for k in ('x','e','material','link_nodes'))
    c=x[e].mean(axis=1);theta=np.arctan2(c[:,1],c[:,0])%(2*np.pi)
    sector=np.round(theta/(2*np.pi/8)).astype(int)%8
    local=(theta-sector*2*np.pi/8+np.pi)%(2*np.pi)-np.pi
    along=local*74.98+9;top=x[np.unique(e[m==2]),2].min()
    layer=np.where(75.01-np.linalg.norm(c[:,:2],axis=1)+c[:,2]-top<2.8,0,1)
    order=[0,4,2,6,1,5,3,7];sequence=[(p,j) for p in range(2) for j in order]
    index={item:i//2 for i,item in enumerate(sequence)}
    birth=np.array([index[(int(p),int(j))]*(18/1.65+18) for p,j in zip(layer,sector)])+np.clip(along/1.65,0,18/1.65)
    cast=np.isin(links[:,1],np.unique(e[m==1]));times=[0,inp['dt_s']];rows=[]
    for t in times:
        occupied=np.unique(e[(m!=2)|(t>=birth)])
        active=np.isin(links[:,0],occupied)
        disconnected=not(np.any(active&cast) and np.any(active&~cast))
        rows.append(dict(time_s=t,QT_active_links=int(np.sum(active&cast)),steel_active_links=int(np.sum(active&~cast)),
            original_policy_gauge=t==0,corrected_policy_gauge=disconnected))
    # Active links only increase. If connected at the first finite increment,
    # both policies omit the seat gauge for every subsequent increment.
    same=all(r['original_policy_gauge']==r['corrected_policy_gauge'] for r in rows)
    result=dict(case=case,first_steps=rows,gauge_schedules_identical_for_this_mesh_and_step=same,
        monotonic_connection_basis='deposition is cumulative; mechanical links follow occupied master nodes',
        initial_seating_guess_correction_scope='the added uniform1e-8mm seat translation changes the Newton initial guess, not constraints or the converged equilibrium; its effect on nonlinear solution selection is not asserted by this schedule audit')
    (folder/'gauge-schedule-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    for p in sorted(OUT.glob('8p-E285-k2500-f2-bore008-*')):
        print(json.dumps(evaluate(p.name),ensure_ascii=False,indent=2))
