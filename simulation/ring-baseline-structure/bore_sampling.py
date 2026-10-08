"""Mesh-independent virtual bore sampling by ray/face intersection.

At each fixed angle and height the radial ray intersects the actual FE bore
facet.  P1/P2 shape functions interpolate the field at that intersection; no
tetrahedral-node averaging or nearest-node snapping is used.
"""
import numpy as np


def sample_surface(points,triangles,displacement,theta,zplanes,order):
    vertices=points[triangles[:,:3]]
    edge1=vertices[:,1]-vertices[:,0];edge2=vertices[:,2]-vertices[:,0]
    coords=[];field=[]
    for angle in theta:
        direction=np.array([np.cos(angle),np.sin(angle),0.])
        matrix=np.stack([edge1,edge2,np.broadcast_to(-direction,edge1.shape)],axis=2)
        keep=abs(np.linalg.det(matrix))>1e-12
        ids=np.flatnonzero(keep);inverse=np.linalg.inv(matrix[keep]);v=vertices[keep]
        for z in zplanes:
            rhs=np.column_stack([-v[:,0,0],-v[:,0,1],np.full(len(v),z)-v[:,0,2]])
            solution=np.einsum("nij,nj->ni",inverse,rhs)
            b,c,r=solution.T
            inside=(b>=-1e-8)&(c>=-1e-8)&(b+c<=1+1e-8)&(r>0)
            candidates=np.flatnonzero(inside)
            if not len(candidates):raise RuntimeError(f"Bore face not found at theta={angle}, z={z}")
            j=candidates[0];L=np.array([1-b[j]-c[j],b[j],c[j]])
            if order==1:N=L
            else:N=np.r_[L*(2*L-1),4*L[0]*L[1],4*L[1]*L[2],4*L[2]*L[0]]
            coords.append([20*direction[0],20*direction[1],z])
            field.append(N@displacement[triangles[ids[j]]])
    return np.array(coords),np.array(field)


def sample_quarter(points,triangles,displacement,theta,zplanes,name):
    mapped=np.arctan2(abs(np.sin(theta)),abs(np.cos(theta)))
    p,u=sample_surface(points,triangles,displacement,mapped,zplanes,2)
    sx=np.where(np.cos(theta)>=0,1.,-1.);sy=np.where(np.sin(theta)>=0,1.,-1.)
    R=np.repeat(np.column_stack([sx,sy,np.ones(len(theta))]),len(zplanes),axis=0)
    parity=np.repeat(sx if name in ("radial","overturning") else np.ones(len(theta)),len(zplanes))
    return p*R,u*R*parity[:,None]
