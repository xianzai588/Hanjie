"""Recover spring forces from the saved stress-free birth reference.

This evaluates the constitutive spring law, rather than inferring a member
force from equilibrium. It does not give the elastic ties plastic capacity.
"""
from pathlib import Path
import argparse,json
import numpy as np
from scipy.sparse import coo_matrix

OUT=Path(__file__).parent/'results'


def actual_force(fields,folder):
    with np.load(folder/'continuation-checkpoint.npz') as cp:
        with np.load(folder/'fields.npz') as original:
            if not all(np.array_equal(cp[k],original[k]) for k in ('x','e')):
                raise ValueError('checkpoint geometry differs from final manufacturing fields')
            if not np.allclose(cp['u'].reshape(-1,3),original['u'],rtol=0,atol=1e-12):
                raise ValueError('checkpoint does not contain the final manufacturing state')
        reference=cp['link_reference'].copy()
        if not np.all(cp['mechanical_link_active']):
            raise ValueError('not all interface springs were born in the final state')
    x,e,m,bd=fields['x'],fields['e'],fields['material'],fields['boundary']
    nodes,weights=fields['link_nodes'],fields['link_weights']
    L=coo_matrix((weights.ravel(),(np.repeat(np.arange(len(nodes)),nodes.shape[1]),nodes.ravel())),shape=(len(nodes),len(x))).tocsr()
    weld_nodes=np.unique(e[m==2]);faces=bd[np.isin(bd[:,0],weld_nodes)]
    area=np.linalg.norm(np.cross(x[faces[:,1]]-x[faces[:,0]],x[faces[:,2]]-x[faces[:,0]]),axis=1)/2
    radial=np.linalg.norm(x[faces,:2],axis=2);z0=x[weld_nodes,2].min()
    picks=[np.all(abs(radial-75)<1e-4,axis=1),np.all(abs(x[faces,2]-z0)<1e-4,axis=1)]
    tributary=[np.bincount(faces.ravel(),weights=np.repeat(area*pick/3,3),minlength=len(x)) for pick in picks]
    cast=np.isin(nodes[:,1],np.unique(e[m==1]))
    link_area=np.where(cast,tributary[1][nodes[:,0]],tributary[0][nodes[:,0]])
    if np.any(link_area<=0):raise ValueError('nonpositive original spring tributary area')
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    density=np.where(cast,75000/1.2,160000/inp['h_mm'])
    jump=L@fields['u']-reference
    force=(density*link_area)[:,None]*jump
    return force,dict(reference=reference,jump=jump,area=link_area,density=density,cast=cast,L=L)


def audit(case):
    from welded_strength import recover_equilibrium_interface
    folder=OUT/case
    with np.load(folder/'free-release-fields.npz') as src:f={k:src[k] for k in src.files}
    direct,state=actual_force(f,folder)
    inferred,errors=recover_equilibrium_interface(f,folder)
    # Rank of L after deletion of gauge nodes governs uniqueness, independent
    # of how small the LSMR equilibrium residual happens to be.
    from scipy.sparse.linalg import eigsh
    release=json.loads((folder/'free-release-verification.json').read_text(encoding='utf8'))
    gauge=np.asarray(release['remaining_gauge_dofs']);eigen=[]
    for axis in range(3):
        free=np.setdiff1d(np.arange(len(f['x'])),gauge[gauge%3==axis]//3)
        A=state['L'][:,free]
        eigen.append(float(eigsh(A@A.T,k=1,which='SA',return_eigenvectors=False,tol=1e-9)[0]))
    difference=np.linalg.norm(direct-inferred,axis=1)
    result=dict(case=case,method='actual k*A*(L*u - saved birth reference), including free-shell release displacement',
        maximum_force_difference_from_LSMR_N=float(difference.max()),
        force_difference_norm_N=float(np.linalg.norm(direct-inferred)),LSMR_equilibrium_residual_N=errors,
        minimum_gauge_restricted_row_gram_eigenvalues=eigen,
        equilibrium_inverse_is_unique=bool(min(eigen)>1e-10),
        actual_spring_law_matches_recovery=bool(difference.max()<.001),
        maximum_actual_traction_MPa={name:float(np.linalg.norm(direct[mask]/state['area'][mask,None],axis=1).max()) for name,mask in [('QT_Ni99',state['cast']),('steel_NiFe',~state['cast'])]},
        scope='verification of forces in the present elastic spring model; local plastic load transfer and Ni99/PMZ capacity require resolved material states')
    np.savez_compressed(folder/'actual-interface-state.npz',force_N=direct,birth_reference_mm=state['reference'],jump_mm=state['jump'],area_mm2=state['area'],density_N_mm3=state['density'],is_QT=state['cast'])
    (folder/'interface-state-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',nargs='+',required=True)
    for c in p.parse_args().cases:print(json.dumps(audit(c),ensure_ascii=False,indent=2),flush=True)
