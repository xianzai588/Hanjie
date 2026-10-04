"""Check actual coupled-run segment start records and their source stage timing."""
from pathlib import Path
import json
import numpy as np

OUT=Path(__file__).parent/'results'
# Retained only for early runs that predated in-run temperature instrumentation.
REPLAYS={'8p-birthpatch-h20-dt025-s05':'process-temperature-h20-dt025',
         '8p-birthpatch-h15-dt025-s05':'process-temperature-h15-dt025'}


def main():
    cases=json.loads((OUT/'verification.json').read_text(encoding='utf8'))['cases']
    direct=[];replays=[]
    for name in cases:
        folder=OUT/name
        inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
        completed=json.loads((folder/'result.json').read_text(encoding='utf8'))
        start_file=folder/'process-start-temperatures.json'
        provenance='recorded within the actual coupled run'
        if not start_file.exists():
            replay_name=REPLAYS.get(name)
            if replay_name is None:raise RuntimeError('missing actual segment-start record: '+name)
            replay=OUT/replay_name
            replay_inp=json.loads((replay/'input.json').read_text(encoding='utf8'))
            keys=['materials','sequence','travel_mm_s','net_W','h_mm','dt_s','source_radius_mm',
                'source_depth_mm','source_r_mm','seat_geometry','copper_contact_W_m2K',
                'copper_water_inlet_C','Ni99_thin_layer_mm','Ni99_conductivity_W_mK',
                'paired_opposed_sources','stage_sequence']
            same=all(replay_inp.get(k)==inp.get(k) for k in keys)
            for k in ['copper_heat_capacity_J_K','water_lumped_design_W_K','copper_effective_area_mm2']:
                same=same and replay_inp['copper_water_model'][k]==inp['copper_water_model'][k]
            thermal=np.loadtxt(replay/'thermal-history.csv',delimiter=',',skiprows=1)
            coupled=np.loadtxt(folder/'thermal-history.csv',delimiter=',',skiprows=1)
            difference=max(float(np.max(abs(thermal[:,col]-np.interp(thermal[:,0],coupled[:,0],coupled[:,col])))) for col in [1,2,7,8])
            if not same or difference>1e-4:raise RuntimeError('thermal replay does not match actual coupled source: '+name)
            replays.append(dict(thermal_case=replay_name,coupled_case=name,input_physics_identical=same,maximum_heat_history_difference_C=difference))
            start_file=replay/'process-start-temperatures.json'
            provenance='actual thermal replay matched to full coupled thermal history'
        starts=json.loads(start_file.read_text(encoding='utf8'))
        ordered=len(starts)==len(inp['sequence']) and [(r['pass_index'],r['segment_number']-1) for r in starts]==[tuple(v) for v in inp['sequence']]
        stages=inp.get('stage_sequence',[[item] for item in inp['sequence']])
        interval=18/inp['travel_mm_s']+inp['idle_s']
        stage_index={tuple(item):i for i,stage in enumerate(stages) for item in stage}
        timing=all(abs(r['t_s']-stage_index[(r['pass_index'],r['segment_number']-1)]*interval)<1e-7 for r in starts)
        temperatures=all(r['process_temperature_pass'] and r['start_max_C']<=r['temperature_limit_C'] for r in starts)
        valid=ordered and timing and completed['released'] and temperatures
        direct.append(dict(coupled_case=name,start_record_source=str(start_file.relative_to(OUT)),
            start_record_provenance=provenance,ordered_segment_starts=ordered,source_stage_times_match=timing,
            temperature_design_pass=bool(valid),maximum_start_C=max(r['start_max_C'] for r in starts),
            simultaneous_heads=inp.get('maximum_simultaneous_heads',1)))
    summary=dict(records=replays,coupled_start_records=direct,
        process_temperature_design_pass=bool(len(direct)==3 and all(r['temperature_design_pass'] for r in direct)),
        maximum_start_C=max(r['maximum_start_C'] for r in direct),
        measurement='actual QT fixed R61 top-face points relative to final weld toe; cover checks previous root node maximum',
        scope='actual coupled temperature records at every source stage; nominal 18 s interstage operations; physical thermometry and 400-500 C peening remain WPS controls')
    (OUT/'process-temperature-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
