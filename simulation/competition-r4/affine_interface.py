"""Linear-complete interface interpolation, including rigid-body rotations."""
import numpy as np
from scipy.spatial import cKDTree

def interface_links(x, targets, picked, planar=False):
    tree=cKDTree(x[targets])
    count=min(16,len(targets))
    links=[]
    for node in picked:
        distance,index=tree.query(x[node],k=count)
        host=targets[index]
        if distance[0]<1e-7:
            weights=np.zeros(count);weights[0]=1.
        else:
            delta=x[host]-x[node]
            scale=max(np.sqrt(np.mean(np.sum(delta*delta,axis=1))),1e-8)
            coordinates=delta[:,:2] if planar else delta
            a=np.vstack((np.ones(count),(coordinates/scale).T))
            metric=1/np.maximum(distance,1e-6)
            b=a*metric[None,:]
            rhs=np.zeros(len(a));rhs[0]=1
            weights=metric*(np.linalg.pinv(b,rcond=1e-12)@rhs)
        mismatch=np.linalg.norm(weights@x[host]-x[node])
        if mismatch>1e-7 or abs(weights.sum()-1)>1e-9:
            raise RuntimeError(f'interface affine patch failed: node {node}, error {mismatch}')
        if np.sum(abs(weights))>4:
            raise RuntimeError(f'interface extrapolation too large: node {node}, L1={np.sum(abs(weights))}')
        links.append((int(node),host.tolist(),weights.tolist()))
    return links

def audit(x, links):
    nodes=np.array([[link[0],*link[1]] for link in links])
    weights=np.array([[1,*[-w for w in link[2]]] for link in links])
    delta=np.einsum('li,lij->lj',weights,x[nodes])
    return dict(method='16-neighbour distance-weighted least-norm interpolation with exact constant and linear reproduction; planar QT and curved steel patches',
                maximum_affine_coordinate_error_mm=float(np.linalg.norm(delta,axis=1).max()),
                maximum_host_weight_L1=float(np.abs(weights[:,1:]).sum(axis=1).max()),
                rigid_translation_and_rotation_patch_pass=bool(np.linalg.norm(delta,axis=1).max()<1e-7 and np.abs(weights.sum(axis=1)).max()<1e-9))

def birth_continuation(x, occupied, added):
    """Extend displacement to new filler nodes with a complete affine patch.

    Widen only the host cloud when the nearest 16 hosts make extrapolation
    unstable. Never replace a failed rigid-rotation patch with IDW weights.
    """
    tree=cKDTree(x[occupied]); rows=[];maximum_error=0.;maximum_l1=0.;maximum_hosts=0
    for node in added:
        for count in (16,32,64,128):
            count=min(count,len(occupied))
            distance,index=tree.query(x[node],k=count);host=occupied[index]
            delta=x[host]-x[node];scale=max(np.sqrt(np.mean(np.sum(delta*delta,axis=1))),1e-8)
            a=np.vstack((np.ones(count),(delta/scale).T));metric=1/np.maximum(distance,1e-6)
            rhs=np.array([1.,0,0,0])
            if count==16:
                # Preserve the original continuation when its patch passes.
                weights=np.linalg.pinv(a,rcond=.02)[:,0];weights/=weights.sum()
            else:weights=metric*(np.linalg.pinv(a*metric[None,:],rcond=1e-12)@rhs)
            error=np.linalg.norm(weights@delta);l1=float(np.sum(abs(weights)))
            if error<1e-7 and abs(weights.sum()-1)<1e-9 and l1<=4:
                rows.append((host,weights));maximum_error=max(maximum_error,float(error));maximum_l1=max(maximum_l1,l1);maximum_hosts=max(maximum_hosts,count)
                break
        else:raise RuntimeError(f'new filler affine patch failed at node {node}: error {error}, L1 {l1}')
    return rows,dict(maximum_coordinate_error_mm=maximum_error,maximum_host_weight_L1=maximum_l1,maximum_host_count=maximum_hosts,new_node_count=len(added))
