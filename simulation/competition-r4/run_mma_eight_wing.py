"""Actual sequential eight-wing first layer, preserving each prior nodal state."""
import argparse
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT
from run_mma_startup_check import arguments
from run_ni99_precoat_first import run


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--mesh',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True)
    p.add_argument('--stop-time',type=float)
    p.add_argument('--phase-resolved-cooling-dt',type=float)
    p.add_argument('--endpoint-from',type=lambda s:ROOT/s)
    p.add_argument('--endpoint-time',type=float,default=11.569017260119475)
    p.add_argument('--threads',type=int,choices=[1,2,4,8],default=1)
    a=p.parse_args()
    config=arguments(a.mesh,a.output,.125,False,a.stop_time,3.,'bottom_up')
    config.all_wings=True
    config.record_nodal_history=True
    config.transient_from=a.endpoint_from;config.transient_time=a.endpoint_time
    config.phase_resolved_cooling_dt_s=a.phase_resolved_cooling_dt
    with threadpool_limits(limits=a.threads):run(config)
