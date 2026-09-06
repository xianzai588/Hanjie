"""角接头参考几何、连续填丝体积与可见表面热源；不修改旧焊缝带。"""
from __future__ import annotations

import math

import numpy as np
from scipy.special import erf


def _edges(anchors, near, far, zone):
    anchors = np.unique(anchors)
    result = [anchors[0]]
    for lo,hi in zip(anchors[:-1],anchors[1:]):
        step = near if lo>=zone[0] and hi<=zone[1] else far
        result.extend(np.linspace(lo,hi,max(1,math.ceil((hi-lo)/step))+1)[1:])
    return np.asarray(result)


def build_geometry(config, process_input, spec):
    grid,mesh = config["thermal_grid"],spec["mesh"]
    p = process_input["process"]["nominal"]
    speed = config["process"]["travel_speed_mm_s"]
    efficiency = spec["deposition"]["efficiency"]
    if not 0<efficiency<=1 or p["filler_feed_rate_mm_s"]<=0 or speed<=0:
        raise ValueError("填丝效率、送丝速度和行走速度无效")
    area = np.pi*p["filler_diameter_mm"]**2/4*p["filler_feed_rate_mm_s"]/speed*efficiency
    leg = float(np.sqrt(2*area))
    gap = config["geometry"]["interface_gap_nominal_mm"]
    if not 0<=gap<leg:
        raise ValueError("接口间隙必须非负且小于推导填丝焊脚")
    strips = int(mesh["bead_strips"])
    if strips<2:
        raise ValueError("填丝截面至少需要两层")
    bead_z = np.linspace(0.,leg,strips+1)
    widths = leg-(bead_z[:-1]+bead_z[1:])/2
    n = _edges([grid["radial_min_offset_mm"],-5.,-leg,*(-widths),-gap,0.,grid["radial_max_offset_mm"]],mesh["near_spacing_mm"],mesh["far_spacing_mm"],(-5.,5.))
    z = _edges([grid["axial_min_offset_mm"],-4.,*bead_z,4.,grid["axial_max_offset_mm"]],mesh["near_spacing_mm"],mesh["far_spacing_mm"],(-4.,4.))
    path = config["heat_source_path"]
    s = _edges([grid["arc_min_offset_mm"],path["source_start_s_mm"],path["source_end_s_mm"],grid["arc_max_offset_mm"]],mesh["arc_spacing_mm"],mesh["arc_spacing_mm"],(-np.inf,np.inf))
    nc,zc = (n[:-1]+n[1:])/2,(z[:-1]+z[1:])/2
    nn,zz = np.meshgrid(nc,zc,indexing="ij")
    ids2 = np.zeros(nn.shape,dtype=np.int8)
    ids2[(nn<=-gap)&(zz<0)] = 2
    ids2[nn>0] = 1
    # 每个水平条带使用中点宽度，三角形线性边界的面积积分严格相等。
    strip_ids = np.clip(np.searchsorted(bead_z,zz,side="right")-1,0,strips-1)
    bead = (zz>0)&(zz<leg)&(nn<0)&(nn>=-widths[strip_ids])
    if np.any(bead&(ids2!=0)):
        raise ValueError("填丝几何与原有母材重叠")
    ids2[bead] = 3
    ds,dn,dz = np.diff(s),np.diff(n),np.diff(z)
    areas2 = dn[:,None]*dz[None,:]
    bead_area = float(areas2[ids2==3].sum())
    if not np.isclose(bead_area,area,rtol=1e-12,atol=1e-12):
        raise ValueError("离散填丝截面面积不守恒")
    shape = (len(ds),len(dn),len(dz))
    ids3 = np.broadcast_to(ids2,shape).copy()
    occupied = ids3>0
    lattice = np.full(shape,-1,dtype=np.int64)
    lattice[occupied] = np.arange(occupied.sum())
    index = np.array(np.where(occupied)).T
    cell_ids = ids3[occupied]
    dims = np.column_stack((ds[index[:,0]],dn[index[:,1]],dz[index[:,2]]))
    volumes = dims.prod(axis=1)
    left = s[index[:,0]]
    edges_i,edges_j,edges_axis,edges_area,edges_distance = [],[],[],[],[]
    for axis in range(3):
        a,b = [slice(None)]*3,[slice(None)]*3
        a[axis],b[axis] = slice(None,-1),slice(1,None)
        li,lj = lattice[tuple(a)],lattice[tuple(b)]
        valid = (li>=0)&(lj>=0)
        i,j = li[valid],lj[valid]
        edges_i.extend(i); edges_j.extend(j)
        edges_axis.extend(np.full(len(i),axis))
        edges_area.extend(volumes[i]/dims[i,axis])
        edges_distance.extend((dims[i,axis]+dims[j,axis])/2)
    return dict(s_edges=s,n_edges=n,z_edges=z,ids2=ids2,ids=cell_ids,lattice=lattice,index=index,
                dims=dims,volumes=volumes,s_left=left,bead_area_mm2=bead_area,wire_area_per_length_mm2=float(area),
                deposited_leg_mm=leg,gap_mm=gap,
                edge_i=np.asarray(edges_i,int),edge_j=np.asarray(edges_j,int),edge_axis=np.asarray(edges_axis,int),
                edge_area=np.asarray(edges_area,float),edge_distance=np.asarray(edges_distance,float))


def filled_fraction(geometry, source_start, source_end, deposited_length):
    """单元内沿s连续填充；任意时刻都满足积分送丝体积，而非按整单元跳变。"""
    finish = min(source_end,source_start+max(0.,deposited_length))
    overlap = np.clip(np.minimum(geometry["s_left"]+geometry["dims"][:,0],finish)-np.maximum(geometry["s_left"],source_start),0.,geometry["dims"][:,0])
    return np.where(geometry["ids"]==3,overlap/geometry["dims"][:,0],1.)


def surface_weights(geometry, with_bead, width):
    """对45°入射射线的首个材料表面解析积分，不按活动面积再归一化。"""
    if width<=0:
        raise ValueError("表面热源宽度必须为正")
    n,z,ids = geometry["n_edges"],geometry["z_edges"],geometry["ids2"]
    active = (ids>0)&((ids!=3)|with_bead)
    faces = []
    root2 = np.sqrt(2.)
    for j,k in zip(*np.where(active)):
        # 来流沿(+n,-z)，仅左面与上面可能接收；u=(n+z)/sqrt(2)。
        if j==0 or not active[j-1,k]:
            faces.append(((n[j]+z[k])/root2,(n[j]+z[k+1])/root2,1.,-root2*n[j],j,k))
        if k==active.shape[1]-1 or not active[j,k+1]:
            faces.append(((n[j]+z[k+1])/root2,(n[j+1]+z[k+1])/root2,-1.,root2*z[k+1],j,k))
    cuts = np.unique([value for face in faces for value in face[:2]])
    weights = np.zeros_like(ids,dtype=float)
    for lo,hi in zip(cuts[:-1],cuts[1:]):
        mid = (lo+hi)/2
        visible = [face for face in faces if face[0]<=mid<=face[1]]
        if not visible:
            continue
        face = max(visible,key=lambda f:f[2]*mid+f[3])
        fraction = .5*(erf(np.sqrt(3.)*hi/width)-erf(np.sqrt(3.)*lo/width))
        weights[face[4],face[5]] += fraction
    return weights


def longitudinal_integral(lo,hi,center,af,ar,ff,fr):
    """无限域归一化的前后双高斯在有限s区间的积分。"""
    lower,upper = np.asarray(lo)-center,np.asarray(hi)-center
    rear = fr*ar*(erf(np.sqrt(3)*np.minimum(upper,0)/ar)-erf(np.sqrt(3)*np.minimum(lower,0)/ar))
    front = ff*af*(erf(np.sqrt(3)*np.maximum(upper,0)/af)-erf(np.sqrt(3)*np.maximum(lower,0)/af))
    return (rear+front)/(ff*af+fr*ar)


def source_power(geometry, weights_bare, weights_bead, source_start, source_end, center, source, power):
    s = geometry["s_edges"]
    args = (center,source["a_front_mm"],source["a_rear_mm"],source["front_fraction"],source["rear_fraction"])
    whole = longitudinal_integral(s[:-1],s[1:],*args)
    lo,hi = np.maximum(s[:-1],source_start),np.minimum(s[1:],min(center,source_end))
    hi = np.maximum(hi,lo)
    deposited = longitudinal_integral(lo,hi,*args)
    i,j,k = geometry["index"].T
    result = power*((whole[i]-deposited[i])*weights_bare[j,k]+deposited[i]*weights_bead[j,k])
    if np.any(result< -1e-10) or result.sum()>power*(1+1e-10):
        raise ValueError("表面射线积分出现负功率或超额沉积")
    return result


def face_geometry(geometry, fraction):
    i,j,axis = geometry["edge_i"],geometry["edge_j"],geometry["edge_axis"]
    active = fraction>0
    area = geometry["edge_area"]*np.where(axis==0,(active[i]&active[j]).astype(float),np.minimum(fraction[i],fraction[j]))
    distance = geometry["edge_distance"].copy()
    along = axis==0
    distance[along] = (geometry["dims"][i[along],0]*fraction[i[along]]+geometry["dims"][j[along],0]*fraction[j[along]])/2
    distance = np.maximum(distance,1e-30)
    ds,dn,dz = geometry["dims"].T
    exposed = 2*dn*dz*active+2*ds*fraction*(dn+dz)
    np.add.at(exposed,i,-area); np.add.at(exposed,j,-area)
    si,ni,zi = geometry["index"].T
    # s端面、QT远场截断面和壳体轴向截断面为绝热人工边界。
    exposed -= ((si==0)|(si==len(geometry["s_edges"])-2))*dn*dz*active
    exposed -= (ni==0)*ds*fraction*dz
    exposed -= ((geometry["ids"]==1)&((zi==0)|(zi==len(geometry["z_edges"])-2)))*ds*fraction*dn
    if exposed.min() < -1e-9:
        raise ValueError("接触面重复扣减导致负暴露面积")
    return area,distance,np.maximum(0.,exposed)
