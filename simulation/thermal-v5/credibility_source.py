"""0.4R射线源情景；保持无限投影平面功率定义及有限材料吸收账本。"""
import numpy as np
from scipy.special import erf


def projected_weights(g, with_bead, width, angle_deg=45., penetration_fraction=0., attenuation_length_mm=.5):
    if not (0 < angle_deg < 90 and width > 0 and 0 <= penetration_fraction <= 1 and attenuation_length_mm > 0):
        raise ValueError("入射角、源宽度或穿透参数无效")
    sn,cs = np.sin(np.deg2rad(angle_deg)),np.cos(np.deg2rad(angle_deg))
    n,z,ids = g["n_edges"],g["z_edges"],g["ids2"]
    active = (ids>0)&((ids!=3)|with_bead)
    faces = []
    for j,k in zip(*np.where(active)):
        if j==0 or not active[j-1,k]:
            faces.append((n[j]*cs+z[k]*sn,n[j]*cs+z[k+1]*sn,cs/sn,-n[j]/sn,j,k))
        if k==active.shape[1]-1 or not active[j,k+1]:
            faces.append((n[j]*cs+z[k+1]*sn,n[j+1]*cs+z[k+1]*sn,-sn/cs,z[k+1]/cs,j,k))
    cuts = np.unique([v for f in faces for v in f[:2]])
    surface = np.zeros_like(ids,dtype=float)
    for lo,hi in zip(cuts[:-1],cuts[1:]):
        mid = (lo+hi)/2
        visible = [f for f in faces if f[0]<=mid<=f[1]]
        if visible:
            f = max(visible,key=lambda f:f[2]*mid+f[3])
            surface[f[4],f[5]] += .5*(erf(np.sqrt(3)*hi/width)-erf(np.sqrt(3)*lo/width))
    if penetration_fraction==0:
        return surface
    # 独立射线-矩形求交，沿实际材料路径衰减；间隙不吸收，未捕获功率不补回。
    j,k = np.where(active)
    du = .002
    rays = np.arange(-4*width+du/2,4*width,du)
    volume = np.zeros_like(surface)
    for begin in range(0,len(rays),128):
        u = rays[begin:begin+128,None]
        entry = np.minimum((u*cs-n[j])/sn,(z[k+1]-u*sn)/cs)
        leave = np.maximum((u*cs-n[j+1])/sn,(z[k]-u*sn)/cs)
        length = np.maximum(entry-leave,0.)
        order = np.argsort(-entry,axis=1)
        ordered = np.take_along_axis(length,order,axis=1)
        prior = np.cumsum(ordered,axis=1)-ordered
        absorbed = np.exp(-prior/attenuation_length_mm)*(-np.expm1(-ordered/attenuation_length_mm))
        weight = np.sqrt(3/np.pi)/width*np.exp(-3*(u/width)**2)*du
        values = np.zeros_like(absorbed)
        np.put_along_axis(values,order,absorbed*weight,axis=1)
        np.add.at(volume,(j,k),values.sum(axis=0))
    return (1-penetration_fraction)*surface+penetration_fraction*volume
