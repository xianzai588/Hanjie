"""Fixed-plane Gaussian quadrature, loaded only at the first ray/metal hit.

The moving planar quadrature never renormalizes to the exposed birth volume.
Topmost projected triangle wins; lower upward facets are physically shadowed.
"""
import numpy as np
from scipy.spatial import cKDTree


def load(x,face,xyz,owner,projection,wet,source,width,power,grid_step):
    if grid_step<=0 or width<=0:raise ValueError('positive source quadrature required')
    half=int(np.ceil(4*width/grid_step));uv=(np.arange(-half,half)+.5)*grid_step
    gx,gy=np.meshgrid(uv,uv,indexing='ij');offset=np.c_[gx.ravel(),gy.ravel()]
    point=offset+np.asarray(source)[:2];weight=np.exp(-np.sum(offset**2,axis=1)/width**2)*grid_step**2/(np.pi*width**2)
    if weight.sum()>1+1e-6:raise RuntimeError('planar Gaussian quadrature exceeds analytic power')
    tree=cKDTree(point)
    height=np.full(len(point),-np.inf);hit=np.full(len(point),-1,int);hit_bary=np.zeros((len(point),3))
    exposed=np.flatnonzero(wet&(projection>1e-10))
    cent=xyz[exposed,:,:2].mean(axis=1);radius=np.linalg.norm(xyz[exposed,:,:2]-cent[:,None],axis=2).max(axis=1)
    possible=tree.query_ball_point(cent,radius+1e-8)
    for face_id,indices in zip(exposed,possible):
        if not indices:continue
        ids=np.asarray(indices);v=xyz[face_id];a=v[1,:2]-v[0,:2];b=v[2,:2]-v[0,:2];p=point[ids]-v[0,:2]
        det=a[0]*b[1]-a[1]*b[0]
        l1=(p[:,0]*b[1]-p[:,1]*b[0])/det;l2=(a[0]*p[:,1]-a[1]*p[:,0])/det
        bary=np.c_[1-l1-l2,l1,l2];inside=np.all(bary>=-1e-9,axis=1)
        z=bary@v[:,2];visible=inside&(z>height[ids]+1e-8)
        use=ids[visible];height[use]=z[visible];hit[use]=face_id;hit_bary[use]=bary[visible]
    seen=hit>=0;f=hit[seen];p=power*weight[seen]
    q=np.bincount(face[f].ravel(),weights=(p[:,None]*hit_bary[seen]).ravel(),minlength=len(x))
    per_owner=np.bincount(owner[f],weights=p,minlength=int(owner.max()+1))
    return q,per_owner,dict(reference_gaussian_integral=float(weight.sum()),
        intercepted_fraction=float(weight[seen].sum()),incident_plane_samples=len(point),visible_samples=int(seen.sum()),
        grid_step_mm=grid_step,normalization='fixed analytic pi*w^2; first upward ray/metal hit only; no edge redistribution')
