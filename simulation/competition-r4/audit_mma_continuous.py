"""Audit one completed continuous CI-A1 history, retaining its actual fields."""
import argparse
import json
from pathlib import Path
import numpy as np
from audit_mma_three_cases import audit, ROOT


def evaluate(folder):
    summary, _, _, centres, minimum = audit(folder)
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    birth=np.loadtxt(folder/'deposition-history.csv',delimiter=',',skiprows=1,ndmin=2)
    history=np.loadtxt(folder/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
    source=np.loadtxt(folder/'source-partition-history.csv',delimiter=',',skiprows=1,ndmin=2)
    path=np.loadtxt(folder/'source-path-history.csv',delimiter=',',skiprows=1,ndmin=2)
    cycles=np.load(folder/'interface-cycles.npz')
    temperatures=cycles['nodal_temperature_C']
    times=cycles['time_s']
    threshold=summary['full_liquid_threshold_C']
    summary.update(
        completed_arc_duration_s=inp['tracks'][0]['arc_duration_s'],
        arc_track_count=len(inp['tracks']),
        actual_deposited_mass_g=float(birth[-1,5]),
        prescribed_deposited_mass_g=inp['integrated_deposited_mass_g'],
        maximum_step_mass_error_g=float(abs(birth[:,2]-birth[:,3]).max()),
        maximum_cumulative_mass_error_g=float(abs(birth[:,4]-birth[:,5]).max()),
        maximum_disconnected_deposit_mm3=float(birth[:,9].max()),
        source_domain_times='all Gaussian coordinates and source occupancy at midpoint; capacity at implicit end time',
        source_midpoint_domain_recorded=bool(path.shape[1]==10),
        source_fraction_to_Ni_range=(source[:,11]/source[:,6]).take([np.argmin(source[:,11]/source[:,6]),np.argmax(source[:,11]/source[:,6])]).tolist(),
        source_wire_partition_max_error_J=float(abs(source[:,4]+source[:,6]+source[:,7]-source[:,5]).max()),
        maximum_relative_step_energy_balance_error=float(np.max(abs(history[:,-1])/np.maximum.reduce([history[:,7],history[:,9],np.ones(len(history))]))),
        energy_check_basis='step balance normalized by max(input,loss,1J); 1e-6 relative criterion covers both arc and zero-input cooling',
        central18mm_every_face_full_liquid_pass=bool(summary['central18mm_min_face_peak_C']>=threshold),
        full_liquid_continuous_intervals_mm=[],
        minimum_recorded_full_liquid_face_duration_s=None,
        thermal_boundary_scope='one wing on complete QT seat; initial300C, free cooling to500C; not eight-wing manufacturing/furnace replay',
        numerical_response_convergence_verified=False,
        physical_source_calibrated=False,
        full_manufacturing_verified=False,
        PMZ_capacity_assigned=False)
    # The historical audit included process-decision flags for its original
    # unqualified scenarios. This audit supplies measured accounting fields;
    # response convergence is decided by the actual comparison driver.
    summary.pop('usable_for_requested_net_energy_decision',None)
    summary.pop('mesh_time_convergence_verified',None)
    qualified=(minimum>=threshold)&(centres>=-9)&(centres<=9)
    indices=np.flatnonzero(qualified)
    if len(indices):
        groups=np.split(indices,np.flatnonzero(np.diff(indices)>1)+1)
        summary['full_liquid_continuous_intervals_mm']=[[float(centres[g[0]]-.125),float(centres[g[-1]]+.125)] for g in groups]
    # Duration is only a recorded-time lower estimate. Do not reconstruct a
    # wetting law or fill absent temperature crossings.
    face_min=temperatures.min(axis=2)
    duration=np.sum(np.diff(times)[:,None]*((face_min[:-1]>=threshold)&(face_min[1:]>=threshold)),axis=0)
    covered=duration>0
    if covered.any():summary['minimum_recorded_full_liquid_face_duration_s']=float(duration[covered].min())
    summary['one_wing_thermal_connection_screen_pass']=bool(
        summary['arc_track_count']==1
        and summary['central18mm_every_face_full_liquid_pass']
        and summary['maximum_disconnected_deposit_mm3']<1e-8
        and summary['maximum_cumulative_mass_error_g']<1e-9
        and summary['maximum_relative_step_energy_balance_error']<1e-6
        and summary['source_wire_partition_max_error_J']<1e-7
        and summary['maximum_temperature_C']<2800)
    summary['qualification_scope']='thermal connection screen under saved model inputs; numerical comparison required before retained-state manufacturing'
    (folder/'continuous-interface-audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=lambda s:ROOT/s,required=True)
    a=p.parse_args()
    print(json.dumps(evaluate(a.run),ensure_ascii=False,indent=2))
