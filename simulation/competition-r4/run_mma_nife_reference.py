"""One bounded ENiFe-CI reference check after the CI-A1 thermal-domain issues."""
import json
from types import SimpleNamespace
import numpy as np
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT,configure
from ni99_local_thermal import tables
from run_ni99_precoat_first import run

if __name__=='__main__':
    mesh=ROOT/'cad/generated/mma-mass-envelope/CI-A2'
    geometry=json.loads((mesh/'geometry-audit.json').read_text())
    _,t,h,_=configure(tables(1300.,.75),'CI-A2')
    entry=float(np.interp(1250000+np.interp(25,t,h),h,t))
    args=SimpleNamespace(mesh=mesh,output=ROOT/'simulation/competition-r4/results/mma-literature-nife-reference',
        power=810.*100/60,travel=100/60,width=3.25,depth=geometry['volume_equivalent_floor_to_top_mm'],
        dt=.125,deposition_temperature=entry,initial_temperature=300.,source_drop=0.,ni1_solidus=1300.,
        ni_k_scale=.75,half_overlap=0.,radial_tracks=2,radial_order='inner_first',start_ramp=0.,start_fraction=1.,
        end_ramp=0.,source_model='mma_volume',surface_grid_step=.15,thermal_bounds='nominal',first_geometry='full_pocket',
        pure_filler_birth=False,resume_from=None,phase_carbon_corner=None,phase_graphite_limit='graphite_allowed',
        phase_temperature_shift=0.,stop_after_tracks=None,mma_profile='CI-A2')
    print('Single ENiFe-CI reference; source Table3 810 J/mm, power1350W, no PMZ capacity assigned',flush=True)
    with threadpool_limits(limits=1):run(args)
