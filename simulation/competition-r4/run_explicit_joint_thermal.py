"""Thermal screen of the real five-solid joint; retains existing global baseline."""
from pathlib import Path
import argparse
import numpy as np
import pypardiso
from scipy.sparse import triu
from threadpoolctl import threadpool_limits
import run_candidate_solver as solver
from ni99_local_thermal import tables


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mesh',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--stop-time',type=float,default=10.90909090909091);p.add_argument('--dt',type=float,default=.125)
    p.add_argument('--ni1-solidus',type=float,default=1300.);p.add_argument('--ni-k-scale',type=float,default=.75)
    p.add_argument('--source-width',type=float,default=1.270170592);p.add_argument('--source-depth',type=float,default=.923760431)
    p.add_argument('--source-r',type=float,default=74.8);p.add_argument('--root-rise',type=float,default=1.2)
    p.add_argument('--root-rise-end',type=float)
    p.add_argument('--root-start-dwell',type=float,default=0.)
    p.add_argument('--phase-carbon-corner',choices=['min_C','max_C'])
    p.add_argument('--phase-graphite-limit',choices=['graphite_allowed','graphite_suppressed'],default='graphite_suppressed')
    p.add_argument('--phase-temperature-shift',type=float,default=0.)
    p.add_argument('--imbalance',type=float,default=.05)
    p.add_argument('--deposition-temperature',type=float)
    a=p.parse_args();all_tables=tables(a.ni1_solidus,a.ni_k_scale)
    phase_overrides=None
    if a.phase_carbon_corner:
        from phase_thermal_tables import overrides
        phase_overrides=overrides(all_tables,a.phase_carbon_corner,a.phase_graphite_limit,a.phase_temperature_shift)
        for index,table in phase_overrides.items():all_tables[index]=table
    extra=all_tables[3:]
    for mat in extra:mat['nominal_properties_20c']['poisson_ratio']=.29
    engine=pypardiso.PyPardisoSolver(mtype=2)
    def solve(A,rhs):
        result=pypardiso.spsolve(triu(A,format='csr'),rhs,solver=engine)
        if np.linalg.norm(A@result-rhs)>.001:raise RuntimeError('thermal sparse-direct residual exceeds0.001')
        return result
    solver.thermal_spsolve=solve;solver.DIRECT_SOLVER_NAME='Intel MKL PARDISO Cholesky, thermal only';solver.SOLVER_THREADS=1
    from joint_interface_thermal import InterfaceThermalObserver
    observer=InterfaceThermalObserver(a.mesh,a.output,all_tables)
    with threadpool_limits(limits=1):
        solver.run(8,1.5,a.dt,a.output,imbalance=a.imbalance,stop_time=a.stop_time,thermal_only=True,contact_density=2500.,copper_h=50.,
          source_radius=a.source_width,source_depth=a.source_depth,weld_h=.5,source_r=a.source_r,seat_path=solver.ROOT/'simulation/competition-r4/geometry/8P-R2-t15.step',
          paired=True,unilateral_pads=True,material_enthalpy=True,initial_bore_diameter=40.008,
          fixture_contact_h=2000.,fixture_refinement=2,net_power=470.25,explicit_mesh_path=a.mesh,additional_material_tables=extra,source_root_rise=a.root_rise,nodal_thermal_observer=observer,deposition_temperature=a.deposition_temperature,source_root_rise_end=a.root_rise_end,material_table_overrides=phase_overrides,source_root_start_dwell=a.root_start_dwell)
    observer.save()
