"""热离散诊断账本：保留逐面界面通量和局部热源空间分配。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


MATERIAL_NAMES = {1: "q235b", 2: "qt450_10", 3: "ernife_ci"}
INTERFACES = {
    frozenset((2, 3)): ("qt450_10_to_ernife_ci", 2, 3),
    frozenset((1, 3)): ("ernife_ci_to_q235b", 3, 1),
}
NAME_TO_MATERIAL = {name: code for code, name in MATERIAL_NAMES.items()}


def _cell_centres(geometry):
    index = np.asarray(geometry["index"], dtype=int)
    return np.column_stack(
        (
            np.asarray(geometry["s_left"], dtype=float) + np.asarray(geometry["dims"], dtype=float)[:, 0] / 2,
            (np.asarray(geometry["n_edges"])[index[:, 1]] + np.asarray(geometry["n_edges"])[index[:, 1] + 1]) / 2,
            (np.asarray(geometry["z_edges"])[index[:, 2]] + np.asarray(geometry["z_edges"])[index[:, 2] + 1]) / 2,
        )
    )


def build_material_point_stencil(geometry, coordinate_s_n_z_mm, material_id, neighbours=8):
    """建立固定物理点的同材料逆距离模板；域外或跨材料立即拒绝。"""
    point = np.asarray(coordinate_s_n_z_mm, dtype=float)
    edges = [np.asarray(geometry[key], dtype=float) for key in ("s_edges", "n_edges", "z_edges")]
    if any(value < edge[0] or value > edge[-1] for value, edge in zip(point, edges)):
        raise ValueError("固定观测点超出计算域，不允许静默外推")
    grid_index = tuple(int(np.searchsorted(edge, value, side="right") - 1) for edge, value in zip(edges, point))
    grid_index = tuple(min(index, len(edge) - 2) for index, edge in zip(grid_index, edges))
    lookup = {tuple(row): cell for cell, row in enumerate(np.asarray(geometry["index"], dtype=int))}
    containing = lookup.get(grid_index)
    ids = np.asarray(geometry["ids"], dtype=int)
    if containing is None or ids[containing] != int(material_id):
        raise ValueError("固定观测点未落入预期材料，不允许跨区域插值")

    centres = _cell_centres(geometry)
    candidates = np.flatnonzero(ids == int(material_id))
    distances = np.linalg.norm(centres[candidates] - point, axis=1)
    order = np.argsort(distances)[: max(1, min(int(neighbours), len(candidates)))]
    selected = candidates[order]
    selected_distance = distances[order]
    exact = np.flatnonzero(selected_distance <= 1e-14)
    if exact.size:
        selected = selected[exact[:1]]
        weights = np.ones(1)
    else:
        inverse = 1 / np.maximum(selected_distance, 1e-14) ** 2
        weights = inverse / inverse.sum()
    return {
        "method": "same_material_inverse_distance_squared",
        "material_id": int(material_id),
        "requested_coordinate_s_n_z_mm": point.tolist(),
        "cell_indices": selected.astype(int).tolist(),
        "cell_centres_s_n_z_mm": centres[selected].tolist(),
        "weights": weights.tolist(),
        "maximum_stencil_radius_mm": float(selected_distance[: len(selected)].max(initial=0.0)),
    }


def aggregate_source_to_lower_cells(lower_field, upper_source_rows):
    """把细网格源能量精确归并到包含它的粗网格物理控制体。"""
    edges = [np.asarray(lower_field[f"{axis}_edges"], dtype=float) for axis in ("s", "n", "z")]
    cross = np.asarray(lower_field["material_cross_section"], dtype=int)
    shape = (len(edges[0]) - 1, *cross.shape)
    occupied = np.broadcast_to(cross > 0, shape)
    lattice = np.full(shape, -1, dtype=int)
    lattice[occupied] = np.arange(int(occupied.sum()))
    lower_ids = np.asarray(lower_field["material_id"], dtype=int)
    result = np.zeros(len(lower_ids))
    for row in upper_source_rows:
        point = np.asarray(row["centre_s_n_z_mm"], dtype=float)
        index = tuple(int(np.searchsorted(edge, value, side="right") - 1) for edge, value in zip(edges, point))
        if any(i < 0 or i >= shape[axis] for axis, i in enumerate(index)):
            raise ValueError("细网格源单元超出粗网格计算域")
        cell = int(lattice[index])
        expected = NAME_TO_MATERIAL[row["material"]]
        if cell < 0 or lower_ids[cell] != expected:
            raise ValueError("嵌套源单元跨越材料区域，无法进行共同控制体比较")
        result[cell] += float(row["cumulative_source_energy_j"])
    return result


def aggregate_interface_faces(lower_field, lower_faces, upper_faces):
    """把细网格逐面累计热量归并到同一粗网格界面面片。"""
    edges = [np.asarray(lower_field[f"{axis}_edges"], dtype=float) for axis in ("s", "n", "z")]

    def key(face):
        axis = int(face["axis"])
        centre = np.asarray(face["centre_s_n_z_mm"], dtype=float)
        orthogonal = tuple(
            int(np.searchsorted(edges[direction], centre[direction], side="right") - 1)
            for direction in range(3)
            if direction != axis
        )
        return face["name"], axis, round(float(centre[axis]), 12), orthogonal

    mapping = {key(face): index for index, face in enumerate(lower_faces)}
    if len(mapping) != len(lower_faces):
        raise ValueError("粗网格界面面片键不唯一")
    result = np.zeros(len(lower_faces))
    for face in upper_faces:
        index = mapping.get(key(face))
        if index is None:
            raise ValueError("细网格界面面片无法映射到共同粗界面")
        result[index] += float(face["cumulative_signed_heat_j"])
    return result


@dataclass
class _PreparedStep:
    dt: float
    dt_conductance: np.ndarray
    face_area: np.ndarray
    active_volume: np.ndarray


class DetailedThermalLedger:
    """在不改变求解器残量的前提下旁路记录数值离散量。"""

    def __init__(self, geometry):
        self.geometry = geometry
        self.ids = np.asarray(geometry["ids"], dtype=int)
        self.centres = _cell_centres(geometry)
        self.edge_i = np.asarray(geometry["edge_i"], dtype=int)
        self.edge_j = np.asarray(geometry["edge_j"], dtype=int)
        self.edge_axis = np.asarray(geometry["edge_axis"], dtype=int)
        self.interface_edges = np.array(
            [edge for edge, (i, j) in enumerate(zip(self.edge_i, self.edge_j)) if frozenset((self.ids[i], self.ids[j])) in INTERFACES],
            dtype=int,
        )
        count = len(self.interface_edges)
        self.face_energy = np.zeros(count)
        self.face_peak_flux = np.zeros(count)
        self.face_max_area = np.zeros(count)
        self.interface_history = []
        self.source_energy = np.zeros(len(self.ids))
        self.source_peak_density = np.zeros(len(self.ids))
        self.source_history = []
        self._prepared = None

    def prepare_step(self, fraction, matrix, dt, face_area):
        if dt <= 0:
            raise ValueError("时间步必须为正")
        selected = self.interface_edges
        dt_conductance = -np.asarray(matrix[self.edge_i[selected], self.edge_j[selected]]).reshape(-1)
        self._prepared = _PreparedStep(
            dt=float(dt),
            dt_conductance=dt_conductance,
            face_area=np.asarray(face_area, dtype=float)[selected],
            active_volume=np.asarray(self.geometry["volumes"], dtype=float) * np.asarray(fraction, dtype=float),
        )

    def record_step(self, temperature, source_power):
        if self._prepared is None:
            raise RuntimeError("必须先记录本时间步的导热矩阵")
        prepared = self._prepared
        temperature = np.asarray(temperature, dtype=float)
        source_power = np.asarray(source_power, dtype=float)
        selected = self.interface_edges
        energy_ij = prepared.dt_conductance * (temperature[self.edge_i[selected]] - temperature[self.edge_j[selected]])
        signed = np.empty_like(energy_ij)
        names = []
        for local, edge in enumerate(selected):
            i, j = self.edge_i[edge], self.edge_j[edge]
            name, source_id, _ = INTERFACES[frozenset((self.ids[i], self.ids[j]))]
            names.append(name)
            signed[local] = energy_ij[local] if self.ids[i] == source_id else -energy_ij[local]
        flux = np.divide(
            signed,
            prepared.dt * prepared.face_area,
            out=np.zeros_like(signed),
            where=prepared.face_area > 0,
        )
        self.face_energy += signed
        self.face_peak_flux = np.maximum(self.face_peak_flux, np.abs(flux))
        self.face_max_area = np.maximum(self.face_max_area, prepared.face_area)
        interface_row = {}
        for name, _, _ in INTERFACES.values():
            mask = np.asarray(names) == name
            interface_row[name] = {
                "signed_heat_j": float(signed[mask].sum()),
                "signed_power_w": float(signed[mask].sum() / prepared.dt),
                "peak_abs_heat_flux_w_per_mm2": float(np.abs(flux[mask]).max(initial=0.0)),
            }
        self.interface_history.append(interface_row)

        step_energy = source_power * prepared.dt
        self.source_energy += step_energy
        density = np.divide(source_power, prepared.active_volume, out=np.zeros_like(source_power), where=prepared.active_volume > 0)
        self.source_peak_density = np.maximum(self.source_peak_density, density)
        positive = step_energy > 0
        centroid = np.average(self.centres[positive], axis=0, weights=step_energy[positive]).tolist() if positive.any() else None
        self.source_history.append(
            {
                "source_energy_j": float(step_energy.sum()),
                "maximum_cell_source_density_w_per_mm3": float(density.max(initial=0.0)),
                "energy_weighted_centroid_s_n_z_mm": centroid,
            }
        )
        self._prepared = None

    def _face_metadata(self, local, edge):
        i, j, axis = self.edge_i[edge], self.edge_j[edge], int(self.edge_axis[edge])
        index_i = np.asarray(self.geometry["index"], dtype=int)[i]
        edges = [np.asarray(self.geometry[key], dtype=float) for key in ("s_edges", "n_edges", "z_edges")]
        bounds = []
        centre = []
        for direction in range(3):
            if direction == axis:
                plane = float(edges[direction][index_i[direction] + 1])
                bounds.append([plane, plane])
                centre.append(plane)
            else:
                lo = float(edges[direction][index_i[direction]])
                hi = float(edges[direction][index_i[direction] + 1])
                bounds.append([lo, hi])
                centre.append((lo + hi) / 2)
        name, source_id, target_id = INTERFACES[frozenset((self.ids[i], self.ids[j]))]
        return {
            "face_index": int(local),
            "name": name,
            "from_material": MATERIAL_NAMES[source_id],
            "to_material": MATERIAL_NAMES[target_id],
            "axis": axis,
            "centre_s_n_z_mm": centre,
            "bounds_s_n_z_mm": bounds,
            "maximum_active_area_mm2": float(self.face_max_area[local]),
            "cumulative_signed_heat_j": float(self.face_energy[local]),
            "peak_abs_heat_flux_w_per_mm2": float(self.face_peak_flux[local]),
        }

    def finish(self):
        faces = [self._face_metadata(local, edge) for local, edge in enumerate(self.interface_edges)]
        interfaces = []
        for name, source_id, target_id in INTERFACES.values():
            selected = [face for face in faces if face["name"] == name]
            history = [row[name] for row in self.interface_history]
            interfaces.append(
                {
                    "name": name,
                    "from_material": MATERIAL_NAMES[source_id],
                    "to_material": MATERIAL_NAMES[target_id],
                    "face_count": len(selected),
                    "cumulative_signed_heat_j": float(sum(face["cumulative_signed_heat_j"] for face in selected)),
                    "peak_abs_interface_power_w": float(max((abs(row["signed_power_w"]) for row in history), default=0.0)),
                    "peak_abs_heat_flux_w_per_mm2": float(max((face["peak_abs_heat_flux_w_per_mm2"] for face in selected), default=0.0)),
                    "most_active_faces": sorted(selected, key=lambda row: abs(row["cumulative_signed_heat_j"]), reverse=True)[:20],
                }
            )

        positive = self.source_energy > 0
        total = float(self.source_energy.sum())
        if total > 0:
            centroid = np.average(self.centres, axis=0, weights=self.source_energy)
            delta = self.centres - centroid
            covariance = np.einsum("ni,nj,n->ij", delta, delta, self.source_energy) / total
        else:
            centroid, covariance = np.full(3, np.nan), np.full((3, 3), np.nan)
        cells = [
            {
                "cell": int(cell),
                "material": MATERIAL_NAMES[int(self.ids[cell])],
                "centre_s_n_z_mm": self.centres[cell].tolist(),
                "volume_mm3": float(self.geometry["volumes"][cell]),
                "cumulative_source_energy_j": float(self.source_energy[cell]),
                "maximum_source_density_w_per_mm3": float(self.source_peak_density[cell]),
            }
            for cell in np.flatnonzero(positive)
        ]
        source = {
            "definition": "表面源实际进入控制体后的局部分配；单元峰值体积源密度仅诊断，准入比较使用共同物理控制体积分。",
            "total_source_energy_j": total,
            "energy_weighted_centroid_s_n_z_mm": centroid.tolist(),
            "energy_weighted_covariance_mm2": covariance.tolist(),
            "effective_spread_s_n_z_mm": np.sqrt(np.maximum(np.diag(covariance), 0)).tolist(),
            "maximum_cell_source_density_w_per_mm3": float(self.source_peak_density.max(initial=0.0)),
            "source_cells": cells,
            "most_energized_cells": sorted(cells, key=lambda row: row["cumulative_source_energy_j"], reverse=True)[:50],
            "steps": self.source_history,
        }
        interface = {
            "definition": "正号按接口名称由前一材料流向后一材料；逐面热量由求解器同一 dt*G 与收敛温度重建。",
            "interfaces": interfaces,
            "faces": faces,
            "steps": self.interface_history,
        }
        return interface, source
