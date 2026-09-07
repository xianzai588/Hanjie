"""0.4R射线源情景；保持无限投影平面功率定义及有限材料吸收账本。"""
import numpy as np
from scipy.special import erf

from hanjie.simulation.neumann_source import gaussian_interval_moments


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


def projected_boundary_faces(g, with_bead, width, angle_deg=45., penetration_fraction=0., attenuation_length_mm=.5):
    """把可见边界拆成显式面片，并对每个面片解析积分横向高斯。"""
    if penetration_fraction != 0:
        raise ValueError("显式边界 Neumann 模型不接受体内穿透分量")
    if not (0 < angle_deg < 90 and width > 0):
        raise ValueError("入射角或源宽度无效")
    sn, cs = np.sin(np.deg2rad(angle_deg)), np.cos(np.deg2rad(angle_deg))
    n, z, ids = g["n_edges"], g["z_edges"], g["ids2"]
    active = (ids > 0) & ((ids != 3) | with_bead)
    candidates = []
    for j, k in zip(*np.where(active)):
        if j == 0 or not active[j - 1, k]:
            candidates.append((n[j] * cs + z[k] * sn, n[j] * cs + z[k + 1] * sn, cs / sn, -n[j] / sn, 1, n[j], j, k))
        if k == active.shape[1] - 1 or not active[j, k + 1]:
            candidates.append((n[j] * cs + z[k + 1] * sn, n[j + 1] * cs + z[k + 1] * sn, -sn / cs, z[k + 1] / cs, 2, z[k + 1], j, k))
    cuts = np.unique([value for face in candidates for value in face[:2]])
    rows = []
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        mid = (lo + hi) / 2
        visible = [face for face in candidates if face[0] <= mid <= face[1]]
        if not visible:
            continue
        face = max(visible, key=lambda item: item[2] * mid + item[3])
        axis, plane, j, k = int(face[4]), float(face[5]), int(face[6]), int(face[7])
        projection = sn if axis == 1 else cs
        n_mid = plane if axis == 1 else (mid - plane * sn) / cs
        z_mid = (mid - plane * cs) / sn if axis == 1 else plane
        rows.append((j, k, axis, plane, lo, hi, (hi - lo) / projection, n_mid, z_mid, *gaussian_interval_moments(lo, hi, width)))
    names = ("j", "k", "axis", "plane_mm", "u_lo_mm", "u_hi_mm", "cross_length_mm", "n_mm", "z_mm", "fraction", "u_first_moment_mm", "u_second_moment_mm2")
    arrays = np.asarray(rows, dtype=float).T if rows else np.empty((len(names), 0))
    result = {name: arrays[index] for index, name in enumerate(names)}
    for name in ("j", "k", "axis"):
        result[name] = result[name].astype(int)
    result.update(model="explicit_boundary_face_neumann", with_bead=bool(with_bead), angle_deg=float(angle_deg), width_mm=float(width))
    return result


def boundary_face_source_power(
    geometry, faces_bare, faces_bead, source_start, source_end, center, source, power, return_face_data=False
):
    """在真实暴露面上得到 W/face，再守恒散射到相邻控制体 RHS。"""
    from mass_closed_geometry import longitudinal_integral

    s = np.asarray(geometry["s_edges"], dtype=float)
    args = (center, source["a_front_mm"], source["a_rear_mm"], source["front_fraction"], source["rear_fraction"])
    whole = longitudinal_integral(s[:-1], s[1:], *args)
    lo, hi = np.maximum(s[:-1], source_start), np.minimum(s[1:], min(center, source_end))
    deposited = longitudinal_integral(lo, np.maximum(hi, lo), *args)
    entries = []
    for state, faces, along in (
        ("bare", faces_bare, whole - deposited),
        ("deposited", faces_bead, deposited),
    ):
        face_count = len(faces["j"])
        if not face_count:
            continue
        i = np.repeat(np.arange(len(along)), face_count)
        face_index = np.tile(np.arange(face_count), len(along))
        fractions = along[i] * faces["fraction"][face_index]
        keep = fractions > 0
        i, face_index, fractions = i[keep], face_index[keep], fractions[keep]
        j, k = faces["j"][face_index], faces["k"][face_index]
        cells = geometry["lattice"][i, j, k]
        if np.any(cells < 0):
            raise ValueError("边界面没有有效的相邻控制体")
        face_power = float(power) * fractions
        area = np.diff(s)[i] * faces["cross_length_mm"][face_index]
        entries.append({
            "state": np.full(len(i), state), "path_cell": i, "cross_face": face_index,
            "adjacent_cell": cells, "axis": faces["axis"][face_index], "plane_mm": faces["plane_mm"][face_index],
            "centre_s_mm": (s[i] + s[i + 1]) / 2, "centre_n_mm": faces["n_mm"][face_index],
            "centre_z_mm": faces["z_mm"][face_index], "u_lo_mm": faces["u_lo_mm"][face_index],
            "u_hi_mm": faces["u_hi_mm"][face_index], "area_mm2": area, "power_w": face_power,
            "average_flux_w_mm2": face_power / area,
        })
    result = np.zeros(len(geometry["ids"]), dtype=float)
    if entries:
        combined = {key: np.concatenate([item[key] for item in entries]) for key in entries[0]}
        np.add.at(result, combined["adjacent_cell"], combined["power_w"])
    else:
        combined = {key: np.array([]) for key in ("state", "path_cell", "cross_face", "adjacent_cell", "axis", "plane_mm", "centre_s_mm", "centre_n_mm", "centre_z_mm", "u_lo_mm", "u_hi_mm", "area_mm2", "power_w", "average_flux_w_mm2")}
    if np.any(result < -1e-10) or result.sum() > power * (1 + 1e-10):
        raise ValueError("显式边界面出现负功率或超额沉积")
    return (result, combined) if return_face_data else result
