"""Atomic, sparse per-increment contact/plastic/reset records.

Each record belongs to an actually converged mechanical state. A legacy
checkpoint cannot acquire the missing prefix retroactively.
"""
from pathlib import Path
import json
import numpy as np


class PathJournal:
    def __init__(self, folder, bore, elements, resume_time=None, anchor_plastic=None, anchor_eqp=None):
        self.folder = Path(folder) / 'nonlinear-path'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.bore = np.asarray(bore)
        self.elements = int(elements)
        self.prefix_available = False
        self.last_time = None
        records = sorted(self.folder.glob('step-*.npz'))
        if not records and resume_time is not None:
            if anchor_plastic is None or anchor_eqp is None:
                raise ValueError('resumed path journal requires the inherited plastic anchor')
            if np.shape(anchor_plastic)!=(self.elements,6) or np.shape(anchor_eqp)!=(self.elements,):
                raise ValueError('inherited journal anchor shape mismatch')
            anchor=self.folder/'anchor.npz'
            if anchor.exists():raise ValueError('anchor exists without its matching journal; inspect the case')
            np.savez_compressed(anchor,t_s=resume_time,plastic=anchor_plastic,eqp=anchor_eqp)
            (self.folder/'anchor-provenance.json').write_text(json.dumps(dict(
                source='strictly validated resumed committed checkpoint',checkpoint_t_s=resume_time,
                prefix_nodal_plastic_paths_available=False),indent=2),encoding='utf8')
        for record in records:
            with np.load(record, allow_pickle=False) as data:
                t = float(data['t_s'])
                if not np.array_equal(data['bore_nodes'], self.bore) or int(data['element_count']) != self.elements:
                    raise ValueError('path journal is for a different discretisation')
            if resume_time is None:
                raise ValueError('fresh solve must use a new path journal directory')
            if t > resume_time + 1e-8:
                orphan = self.folder / 'uncommitted'
                orphan.mkdir(exist_ok=True)
                record.replace(orphan / record.name)
                continue
            if self.last_time is None:
                self.prefix_available = abs(t) < 1e-10
            if self.last_time is not None and t <= self.last_time:
                raise ValueError('path times are not strictly increasing')
            self.last_time = t

    def append(self, t, gap, contact, dl, direction, reset, reset_eqp, active, released):
        if self.last_time is not None and t <= self.last_time + 1e-10:
            raise ValueError('cannot append duplicate/nonmonotone path state')
        if self.last_time is None:
            self.prefix_available = abs(t) < 1e-10
        yielded = np.flatnonzero(dl > 0)
        reset_ids = np.flatnonzero(reset)
        target = self.folder / f'step-{t:016.9f}.npz'
        temporary = target.with_suffix('.pending.npz')
        np.savez_compressed(temporary, t_s=np.array(t), bore_nodes=self.bore,
            element_count=np.array(self.elements), mandrel_gap_mm=gap,
            mandrel_active=np.asarray(contact, bool), released=np.array(released),
            plastic_element=yielded, delta_eqp=dl[yielded],
            delta_plastic_Mandel=dl[yielded, None] * direction[yielded],
            reset_element=reset_ids, eqp_before_reset=reset_eqp,
            active_element=np.packbits(active), active_element_count=np.array(len(active)))
        temporary.replace(target)
        self.last_time = float(t)
        summary = dict(records_from_zero=self.prefix_available, last_converged_t_s=self.last_time,
            all_elements_recorded=True, all_bore_nodes_recorded=True,
            meaning='sparse plastic updates plus thermal resets; omitted plastic entries are exactly zero',
            interval_internal_bound_established=False)
        (self.folder / 'coverage.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
