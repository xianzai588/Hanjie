"""Run only the frozen A/B/C local design cases; no automatic parameter scan."""
from pathlib import Path
from types import SimpleNamespace
import argparse,json
import numpy as np
import yaml
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT,configure,mesh_saved
from ni99_local_thermal import tables
from run_ni99_precoat_first import run


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case',choices=['A','B','C'])
    parser.add_argument('--attempt',default='',help='Fresh numerical-repair output; physical case stays fixed')
    parser.add_argument('--mesh-h',type=float)
    parser.add_argument('--dt',type=float)
    a=parser.parse_args()
    cfg=yaml.safe_load((ROOT/'project/precoat-three-case-study.yaml').read_text(encoding='utf8'))
    case=next(c for c in cfg['cases'] if c['name']==a.case)
    base=ROOT/'simulation/competition-r4/results/mma-literature-three-cases'
    mesh=base/(f'mesh-h{a.mesh_h:g}' if a.mesh_h else 'mesh');mesh_saved(mesh,a.mesh_h or cfg['mesh_size_mm'])
    _,t,h,_=configure(tables(1300.,.75))
    h25=float(np.interp(25,t,h));entry=float(np.interp(cfg['entering_specific_enthalpy_relative25C_J_kg']+h25,h,t))
    args=SimpleNamespace(mesh=mesh,output=base/(a.case+a.attempt),power=case['line_energy_J_mm']*cfg['travel_mm_s'],
        width=cfg['source_radius_mm']*case.get('source_radius_factor',1.),depth=cfg['source_depth_mm'],dt=a.dt or cfg['dt_s'],deposition_temperature=entry,
        travel=cfg['travel_mm_s'],initial_temperature=case['initial_C'],source_drop=0.,ni1_solidus=1300.,
        ni_k_scale=.75,half_overlap=cfg['central_overlap_each_half_mm'],radial_tracks=2,radial_order='inner_first',start_ramp=0.,
        start_fraction=1.,end_ramp=0.,source_model='mma_volume',surface_grid_step=.15,
        thermal_bounds='nominal',first_geometry='full_pocket',pure_filler_birth=False,resume_from=None,
        phase_carbon_corner=None,phase_graphite_limit='graphite_allowed',phase_temperature_shift=0.,
        stop_after_tracks=None,mma_profile=True)
    print('Case',a.case,'net W',args.power,'entering C',entry,flush=True)
    with threadpool_limits(limits=1):run(args)
