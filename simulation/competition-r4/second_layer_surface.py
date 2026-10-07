"""Actual exposed P1 facets for one growing track beside an earlier track."""
import numpy as np


def polygon_moments(xyz,bary):
    if len(xyz)<3:return np.zeros(bary.shape[1])
    centre=xyz.mean(axis=0);bc=bary.mean(axis=0)
    _,_,axes=np.linalg.svd(xyz-centre,full_matrices=False)
    q=(xyz-centre)@axes[:2].T;order=np.argsort(np.arctan2(q[:,1],q[:,0]))
    moment=np.zeros(bary.shape[1])
    for a,b in zip(order,np.roll(order,-1)):
        area=np.linalg.norm(np.cross(xyz[a]-centre,xyz[b]-centre))/2
        moment+=area*(bc+bary[a]+bary[b])/3
    return moment


def triangle_cut(xyz,values,level):
    unit=np.eye(3);inside=values<=level
    points=[unit[j] for j in np.flatnonzero(inside)]
    for a in np.flatnonzero(inside):
        for b in np.flatnonzero(~inside):
            f=(level-values[a])/(values[b]-values[a]);points.append(unit[a]+f*(unit[b]-unit[a]))
    if len(points)<3:return np.zeros(3)
    points=np.array(points);return polygon_moments(points@xyz,points)


def surface(x,e,faces,owners,neighbours,area,birth,front,fraction):
    n=len(x);kind=np.zeros(len(e),np.int8)
    kind[fraction>=1-1e-12]=1
    kind[(fraction>1e-14)&(fraction<1-1e-12)]=2
    exterior=neighbours<0;safe=np.maximum(neighbours,0)
    a=kind[owners];b=np.where(exterior,0,kind[safe])
    nodal=np.zeros(n)
    whole=(a!=b)&(a!=2)&(b!=2)
    np.add.at(nodal,faces[whole].ravel(),np.repeat(area[whole]/3,3))
    for j in np.flatnonzero((a!=b)&((a==2)|(b==2))):
        nodes=faces[j];clipped=triangle_cut(x[nodes],birth.nodal_values[nodes],front)
        other=b[j] if a[j]==2 else a[j]
        moment=area[j]/3-clipped if other==1 else clipped
        nodal[nodes]+=moment
    # The affine deposition front is also a real exposed surface inside each
    # intersected parent tetrahedron. There is no ghost-capacity boundary.
    unit=np.eye(4)
    for local in np.flatnonzero((birth.lo<front)&(birth.hi>front)):
        parent=birth.indices[local];values=birth.values[local];inside=values<front;points=[]
        for a in np.flatnonzero(inside):
            for b in np.flatnonzero(~inside):
                f=(front-values[a])/(values[b]-values[a]);points.append(unit[a]+f*(unit[b]-unit[a]))
        points=np.array(points);nodal[e[parent]]+=polygon_moments(points@x[e[parent]],points)
    return nodal
