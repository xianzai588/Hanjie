"""Small engineering demand checks; not a weld qualification or FE substitute."""
from pathlib import Path
import json
import math
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'studies/COMPETITION-DESIGN'))
from postweld_isolation import evaluate


def integrated_cp(temperatures, values, start, end):
    points = sorted({start, end, *(t for t in temperatures if start < t < end)})
    def cp(t):
        for a, b, ca, cb in zip(temperatures, temperatures[1:], values, values[1:]):
            if a <= t <= b:
                return ca + (cb-ca)*(t-a)/(b-a)
        raise ValueError('Temperature outside the supplied property table')
    return sum((cp(a)+cp(b))*(b-a)/2 for a, b in zip(points, points[1:]))


def ring_demand(area, radius, radial, axial, moment):
    # Symmetric ring group: I=A*R^2/2; conservative peak axial traction.
    axial_peak = abs(axial)/area + 2*abs(moment)/(area*radius)
    radial_average = abs(radial)/area
    return dict(effective_area_mm2=area, radius_mm=radius,
                peak_axial_demand_MPa=axial_peak, radial_average_demand_MPa=radial_average,
                peak_traction_demand_MPa=math.hypot(axial_peak, radial_average),
                scope='uniform circular-group resultant traction, not von Mises or local PMZ stress; no allowable or fatigue strength')


def main():
    spec = yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))
    materials = yaml.safe_load((ROOT/'project/materials.yaml').read_text(encoding='utf8'))['materials']
    geometry = json.loads((ROOT/spec['geometry_manifest']).read_text(encoding='utf8'))
    qt = materials['qt450_10']['temperature_dependent']
    mass = geometry['geometry']['calculated_mass_kg']
    loads = dict(radial=5000, axial=5000, moment=250000)
    throat = 3.50/math.sqrt(2)
    demand = {
        '6P_fillets': ring_demand(6*18*throat, 75, **loads),
        '8P_fillets': ring_demand(8*18*throat, 75, **loads),
        '16_D6_plug_interfaces': ring_demand(16*math.pi*6**2/4, 75, **loads),
    }
    insulation = evaluate()
    result = dict(
        scope='executed analytical requirements only; no candidate has gained fusion/manufacturing qualification',
        design_loads_N_Nmm=loads,
        circular_group_demands=demand,
        plug_probe=dict(hole_count=16, hole_diameter_mm=6, shell_thickness_mm=5,
                        minimum_hole_fill_volume_mm3=16*math.pi*6**2/4*5,
                        caveat='full effective diameter and fusion assumed only to derive requirements; outer-interface design pending'),
        baseline_GTAW=dict(precoat_arc_s=144, precoat_net_kJ=616*144/1000,
                          final_arc_s=288/1.65, final_net_kJ=300*288/1000,
                          total_arc_s=144+288/1.65, total_net_kJ=616*144/1000+300*288/1000,
                          status='historical wide-track baseline, not adopted MMA settings'),
        independent_preheat=dict(seat_mass_kg=mass,
            stored_sensible_heat_kJ={str(t): mass*integrated_cp(qt['temperatures_c'], qt['specific_heat_j_kgk'], 20, t)/1000
                                     for t in [200, 300, 350]},
            scope='unrecessed solid CAD and engineering Cp, excludes tools and deposited layers; not furnace electricity, duration or a stress-reset operation'),
        honing_drain=insulation['honing']['drain_line'],
        engineering_route_qualified=False,
        next_gate='actual first QT interface, final dual fusion, retained layer, PMZ capacity and residual state transfer')
    destination = ROOT/'deliverables/route-probe-results.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
