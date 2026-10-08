"""Fixed-plane Gaussian quadrature, loaded only at the first ray/metal hit.

The moving planar quadrature never renormalizes to the exposed birth volume.
Topmost projected triangle wins; lower upward facets are physically shadowed.
"""
import numpy as np
from scipy.spatial import cKDTree


def load_birth(x,e,material,face,oa,ob,birth,threshold,source,width,power,grid_step):
    """Load only actual free polygons at the midpoint mass-controlled front.

    The parent mesh is unchanged. Polygon vertices carry their original P1
    shape functions, including the cut front inside a partially born cell.
    This fixes the source geometry; it does not calibrate the source width.
    """
    triangles=[]; coefficients=[]; owners=[]; kinds=[]
    centres=x[e].mean(axis=1)
    def polygon(points,nodes,owner,normal,kind):
        points=np.asarray(points)
        if len(points)<3:return
        vertices=points@x[nodes];middle=vertices.mean(axis=0);bm=points.mean(axis=0)
        u,_,_=np.linalg.svd((vertices-middle).T,full_matrices=False)
        uv=(vertices-middle)@u[:,:2]
        order=np.argsort(np.arctan2(uv[:,1],uv[:,0]))
        for i,j in zip(order,np.roll(order,-1)):
            tri=np.array([middle,vertices[i],vertices[j]])
            shape=np.array([bm,points[i],points[j]])
            cross=np.cross(tri[1]-tri[0],tri[2]-tri[0])
            if np.dot(cross,normal)<0:tri=tri[[0,2,1]];shape=shape[[0,2,1]];cross=-cross
            if cross[2]<=1e-12:continue
            triangles.append(tri);coefficients.append(shape);owners.append(owner);kinds.append(kind)
    def clipped(points,values,keep_below):
        values=np.asarray(values);inside=values<=threshold if keep_below else values>=threshold
        result=[points[i] for i in np.flatnonzero(inside)]
        for i in np.flatnonzero(inside):
            for j in np.flatnonzero(~inside):
                delta=values[j]-values[i]
                if delta==0:continue
                t=(threshold-values[i])/delta
                candidate=points[i]+t*(points[j]-points[i])
                if not any(np.max(abs(candidate-q))<1e-12 for q in result):result.append(candidate)
        return result
    neighbour=np.maximum(ob,0)
    exterior=ob<0
    interface=~exterior&(material[oa]!=material[neighbour])
    # Uncovered QT and occupied Ni share the same clipped interface boundary.
    for fi in np.flatnonzero(exterior|interface):
        candidates=[int(oa[fi])] if exterior[fi] else [int(oa[fi]),int(ob[fi])]
        for owner in candidates:
            if material[owner] not in (1,3):continue
            if interface[fi] and material[owner]==3:continue
            nodes=e[owner]
            shape=np.zeros((3,4))
            for k,node in enumerate(face[fi]):shape[k,np.flatnonzero(nodes==node)[0]]=1.
            values=birth.nodal_values[face[fi]]
            points=clipped(shape,values,True) if material[owner]==3 else clipped(shape,values,False) if interface[fi] else shape
            normal=x[face[fi]].mean(axis=0)-centres[owner]
            polygon(points,nodes,owner,normal,'external')
    # The actual moving deposition surface lies inside the cut parent cells.
    unit=np.eye(4)
    crossing=np.flatnonzero((birth.lo<threshold)&(birth.hi>threshold))
    for local in crossing:
        owner=int(birth.indices[local]);values=birth.values[local];inside=values<threshold
        points=[]
        for i in np.flatnonzero(inside):
            for j in np.flatnonzero(~inside):
                t=(threshold-values[i])/(values[j]-values[i])
                points.append(unit[i]+t*(unit[j]-unit[i]))
        normal=np.linalg.solve(x[e[owner]][1:]-x[e[owner]][0],values[1:]-values[0])
        polygon(points,e[owner],owner,normal,'cut_front')
    if not triangles:raise RuntimeError('No upward actual-born surface supports the incident source')
    xyz=np.asarray(triangles);shape=np.asarray(coefficients);owner=np.asarray(owners)
    half=int(np.ceil(4*width/grid_step));uv=(np.arange(-half,half)+.5)*grid_step
    gx,gy=np.meshgrid(uv,uv,indexing='ij');offset=np.c_[gx.ravel(),gy.ravel()]
    point=offset+np.asarray(source)[:2]
    weight=np.exp(-np.sum(offset**2,axis=1)/width**2)*grid_step**2/(np.pi*width**2)
    if weight.sum()>1+1e-6:raise RuntimeError('planar Gaussian quadrature exceeds analytic power')
    tree=cKDTree(point);height=np.full(len(point),-np.inf);hit=np.full(len(point),-1,int);hit_bary=np.zeros((len(point),3))
    cent=xyz[:,:,:2].mean(axis=1);radius=np.linalg.norm(xyz[:,:,:2]-cent[:,None],axis=2).max(axis=1)
    for fi,indices in enumerate(tree.query_ball_point(cent,radius+1e-8)):
        if not indices:continue
        ids=np.asarray(indices);v=xyz[fi];a=v[1,:2]-v[0,:2];b=v[2,:2]-v[0,:2];p=point[ids]-v[0,:2]
        det=a[0]*b[1]-a[1]*b[0]
        l1=(p[:,0]*b[1]-p[:,1]*b[0])/det;l2=(a[0]*p[:,1]-a[1]*p[:,0])/det
        bary=np.c_[1-l1-l2,l1,l2];inside=np.all(bary>=-1e-9,axis=1)
        z=bary@v[:,2];use=ids[inside&(z>height[ids]+1e-8)]
        selected=inside&(z>height[ids]+1e-8)
        height[use]=z[selected];hit[use]=fi;hit_bary[use]=bary[selected]
    seen=hit>=0;f=hit[seen];p=power*weight[seen]
    parent_shape=np.einsum('ij,ijk->ik',hit_bary[seen],shape[f])
    node_ids=e[owner[f]]
    q=np.bincount(node_ids.ravel(),weights=(p[:,None]*parent_shape).ravel(),minlength=len(x))
    per_owner=np.bincount(owner[f],weights=p,minlength=len(e))
    ni=material[owner[f]]==3
    excess=np.einsum('ij,ij->i',parent_shape[ni],birth.nodal_values[node_ids[ni]])-threshold
    if len(excess) and excess.max()>1e-10:raise RuntimeError('Incident source hit unborn deposition geometry')
    projected=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0])[:,2]/2
    diag=dict(reference_gaussian_integral=float(weight.sum()),intercepted_fraction=float(weight[seen].sum()),
        incident_plane_samples=len(point),visible_samples=int(seen.sum()),grid_step_mm=grid_step,
        normalization='fixed analytic pi*w^2; first actual-born upward ray/metal hit; no redistribution',
        source_surface_time='same midpoint cumulative deposited mass as source xy',birth_front_level=float(threshold),
        actual_upward_triangles=len(xyz),actual_cut_front_triangles=int(np.sum(np.asarray(kinds)=='cut_front')),
        upward_QT_projected_area_mm2=float(projected[material[owner]==1].sum()),
        upward_Ni_projected_area_mm2=float(projected[material[owner]==3].sum()),
        hit_Ni_birth_level_excess_max=float(excess.max()) if len(excess) else None,
        parent_shape_partition_error=float(np.max(abs(parent_shape.sum(axis=1)-1))) if len(parent_shape) else 0.,
        nodal_vs_intercepted_power_error_W=float(q.sum()-p.sum()))
    return q,per_owner,diag


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
