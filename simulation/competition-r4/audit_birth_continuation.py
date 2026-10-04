"""Regress complete affine continuation on an actual solved activation history."""
from pathlib import Path
import json, numpy as np
from affine_interface import birth_continuation

OUT=Path(__file__).parent/'results'
def main():
    folder=OUT/'8p-affine-pardiso-h20-dt0125-s025'
    f=np.load(folder/'mesh.npz');x,e,m=f['x'],f['e'],f['material']
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    c=x[e].mean(axis=1);theta=np.arctan2(c[:,1],c[:,0])%(2*np.pi)
    segment=np.round(theta/(2*np.pi/8)).astype(int)%8
    along=((theta-segment*2*np.pi/8+np.pi)%(2*np.pi)-np.pi)*74.98+9
    layer=np.where(75.01-np.linalg.norm(c[:,:2],axis=1)+c[:,2]-inp['weld_base_z_mm']<2.8,0,1)
    seq=[tuple(v) for v in inp['sequence']]
    birth=np.array([seq.index((int(layer[k]),int(segment[k])))*(18/1.65+18)+np.clip(along[k]/1.65,0,18/1.65) if m[k]==2 else -1e6 for k in range(len(e))])
    active=m!=2;audits=[]
    for t in np.loadtxt(folder/'equilibrium-history.csv',delimiter=',',skiprows=1)[:,0]:
        new=(m!=2)|(t>=birth);old=np.unique(e[active]);added=np.setdiff1d(np.unique(e[new]),old)
        if len(added):
            rows,audit=birth_continuation(x,old,added)
            # Arbitrary translation + skew rigid rotation is an analytic oracle.
            rotation=np.array([[0,-.003,.002],[.003,0,-.001],[-.002,.001,0]])
            for node,(host,weights) in zip(added,rows):
                actual=weights@(x[host]@rotation.T+[.01,.02,.03])
                expected=x[node]@rotation.T+[.01,.02,.03]
                if np.linalg.norm(actual-expected)>1e-9:raise ValueError('birth rigid motion regression failed')
            audits.append(dict(t_s=float(t),**audit))
        active=new
    result=dict(scope='actual full 16-segment new-node sets and analytic rigid translation/rotation; no replayed final position claim',
                maximum_coordinate_error_mm=max(r['maximum_coordinate_error_mm'] for r in audits),
                maximum_host_count=max(r['maximum_host_count'] for r in audits),
                maximum_L1=max(r['maximum_host_weight_L1'] for r in audits),
                new_node_count=sum(r['new_node_count'] for r in audits),pass_check=True,records=audits)
    path=Path(__file__).resolve().parents[2]/'output/review/birth-repaired-all-segments.json'
    path.write_text(json.dumps(result,indent=2),encoding='utf8')
    print({k:v for k,v in result.items() if k!='records'},flush=True)
if __name__=='__main__':main()
