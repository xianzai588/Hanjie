"""Run the current pWPS single continuous CI-A1 first-layer track."""
import argparse
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT
from run_mma_startup_check import arguments
from run_ni99_precoat_first import run

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=lambda s: ROOT/s,required=True,help='fresh evidence directory')
    p.add_argument('--dt',type=float,default=.125)
    p.add_argument('--stop-time',type=float)
    p.add_argument('--endpoint-from',type=lambda s:ROOT/s)
    p.add_argument('--endpoint-time',type=float,default=9.375)
    p.add_argument('--phase-resolved-cooling-dt',type=float)
    p.add_argument('--mesh',type=lambda s:ROOT/s)
    a=p.parse_args()
    config=arguments(a.mesh,a.output,a.dt,False,a.stop_time,3.,'bottom_up')
    config.transient_from=a.endpoint_from;config.transient_time=a.endpoint_time
    config.phase_resolved_cooling_dt_s=a.phase_resolved_cooling_dt
    print('CI-A1: one continuous19.281695mm arc, steady0.17g/s; pWPS endpoint current/mass profile and progressive filling',flush=True)
    with threadpool_limits(limits=1):run(config)
