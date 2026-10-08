"""Generate the active ring card from the submission authority, preserving notes."""
from pathlib import Path
import json
import yaml

ROOT=Path(__file__).resolve().parents[2]


def main():
    spec=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())
    path=ROOT/'deliverables/process/ring-final-welding-card.json'
    card=json.loads(path.read_text())
    weld, process=spec['weld_layout'],spec['final_GTAW']
    length=weld['segment_count']*weld['pass_count']*weld['segment_length_mm']
    arc=length/process['travel_speed_mm_s']
    card.update(process_version=spec['version'], source_type='design_pWPS',authority='project/submission-baseline.yaml',
                segments=weld['segment_count'],passes=weld['pass_count'],sequence=weld['sequence'],
                actual_path_per_segment_per_pass_mm=weld['segment_length_mm'],actual_cumulative_path_mm=length,
                effective_weld_length_per_segment_mm=weld['effective_segment_length_mm'],
                effective_connection_length_mm=weld['segment_count']*weld['effective_segment_length_mm'],
                travel_speed_mm_s=process['travel_speed_mm_s'],nominal_net_line_energy_J_mm=process['nominal_net_energy_J_mm'],
                nominal_net_heat_kJ=length*process['nominal_net_energy_J_mm']/1000,arc_on_time_s=arc,
                wire_feed_mm_s=process['wire_feed_mm_s'],wire_length_mm=arc*process['wire_feed_mm_s'],
                wire_reserved_length_mm=arc*process['wire_feed_mm_s']*card['wire_reserve_factor'],
                assembly_tolerances=spec['geometry'],monitoring_design=spec['monitoring_design'],
                precoat_thermal_cycle=spec['material_route']['precoat_thermal_cycle'])
    # This field in the old hand-written JSON was a beam-only result. The full
    # fixture owns its result; no card retains an obsolete 5.053um certificate.
    for key in ('base_fixture_cold_axis_um','fixture_contact_connection_base_and_hot_remaining_um'):
        card.pop(key,None)
    fixture=ROOT/'studies/COMPETITION-DESIGN/results/ring-fixture-feasibility.json'
    card['base_fixture_source']=str(fixture.relative_to(ROOT))
    card['manufacturing_verified']=False
    card['capacity_verified']=False
    path.write_text(json.dumps(card,ensure_ascii=False,indent=2)+'\n')
    print(path)


if __name__=='__main__':main()
