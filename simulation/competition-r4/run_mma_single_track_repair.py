"""One geometry repair: replace the overfilled two-strip envelope by one bead."""
import json
from types import SimpleNamespace
import numpy as np
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT,configure
from ni99_local_thermal import tables
from run_ni99_precoat_first import run

if __name__=='__main__':
    mesh=ROOT/'cad/generated/mma-mass-envelope/CI-A1-single-track'
    geometry=json.loads((mesh/'geometry-audit.json').read_text())
    _,t,h,_=configure(tables(1300.,.75),'CI-A1')
    entry=float(np.interp(1250000+np.interp(25,t,h),h,t))
    args=SimpleNamespace(mesh=mesh,output=ROOT/'simulation/competition-r4/results/mma-single-track-repair',
        power=1215.*100/60,travel=100/60,width=3.2,depth=geometry['volume_equivalent_floor_to_top_mm'],
        dt=.125,deposition_temperature=entry,initial_temperature=300.,source_drop=0.,ni1_solidus=1300.,
        ni_k_scale=.75,half_overlap=0.,radial_tracks=1,radial_order='inner_first',start_ramp=0.,start_fraction=1.,
        end_ramp=0.,source_model='mma_volume',surface_grid_step=.15,thermal_bounds='nominal',first_geometry='full_pocket',
        pure_filler_birth=False,resume_from=None,phase_carbon_corner=None,phase_graphite_limit='graphite_allowed',
        phase_temperature_shift=0.,stop_after_tracks=None,mma_profile='CI-A1')
    print('Single-track geometry repair; same1215 J/mm net reference and material',flush=True)
    with threadpool_limits(limits=1):run(args)
