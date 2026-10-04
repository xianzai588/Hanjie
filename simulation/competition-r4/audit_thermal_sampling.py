"""First-30-second diagnosis of mechanical sampling of the actual heat field.

This does not solve mechanics or predict cold residual position. All tested
cadences observe the same thermal run, isolating missed hot events and jumps.
"""
from pathlib import Path
import json
import numpy as np
from scipy.sparse import triu
import pypardiso
from threadpoolctl import threadpool_limits
import run_verified as rv

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / 'results/diagnostic-first30-thermal-sampling'
cadences = (.5, .25, .125, .0625)
states = {}
observed_hot = None


def observe(t, temperature, active, material, volume):
    global observed_hot
    hot = active & (temperature > 1200)
    if observed_hot is None:
        observed_hot = np.zeros(len(temperature), dtype=bool)
        for step in cadences:
            states[step] = dict(last_t=0., last_T=np.full(len(temperature), 20.),
                hot=np.zeros(len(temperature), dtype=bool), max_jump=0., max_birth_jump=0.,
                last_active=(material!=2), count=0)
    observed_hot |= hot
    for step, state in states.items():
        if t-state['last_t'] >= step-1e-8:
            state['hot'] |= hot
            continuing=active & state['last_active']
            born=active & ~state['last_active']
            state['max_jump'] = max(state['max_jump'], float(np.max(abs(temperature[continuing]-state['last_T'][continuing]))))
            if np.any(born):
                state['max_birth_jump']=max(state['max_birth_jump'],float(np.max(abs(temperature[born]-20.))))
            state['last_T'] = temperature.copy()
            state['last_active'] = active.copy()
            state['last_t'] = t
            state['count'] += 1
    observe.material, observe.volume = material, volume


def main():
    solver = pypardiso.PyPardisoSolver(mtype=2)
    def solve(matrix, rhs):
        answer = pypardiso.spsolve(triu(matrix, format='csr'), rhs, solver=solver)
        if np.linalg.norm(matrix@answer-rhs) > .001:
            raise RuntimeError('thermal diagnostic linear residual exceeds 0.001')
        return answer
    rv.spsolve = solve
    rv.thermal_spsolve = solve
    rv.structural_spsolve = solve
    rv.SOLVER_THREADS = 2
    with threadpool_limits(limits=2):
        rv.run(8, 2., .0625, OUT, imbalance=.05, preheat=20., stop_time=30.,
            thermal_only=True, struct_dt=.125, contact_density=2000., copper_h=50.,
            source_radius=1.270170592, source_depth=.923760431, weld_h=1.,
            source_r=74.8, cold_struct_dt=2.5,
            seat_path=Path('simulation/competition-r4/geometry/8P-R2-t15.step'),
            thermal_observer=observe)
    rows=[]
    for step, state in states.items():
        parts=[]
        for i, label in enumerate(('steel', 'QT', 'NiFe')):
            mask=observe.material==i
            parts.append(dict(material=label,
                actually_above_annealing_mm3=float(observe.volume[mask & observed_hot].sum()),
                missed_hot_volume_mm3=float(observe.volume[mask & observed_hot & ~state['hot']].sum())))
        rows.append(dict(structural_cadence_s=step, samples=state['count'],
            maximum_continuing_element_temperature_jump_C=state['max_jump'],
            maximum_born_element_temperature_above_ambient_C=state['max_birth_jump'], hot_event_sampling=parts))
    result=dict(scope='same actual first-30-second thermal field; endpoint-sampling diagnosis only, no mechanics or cold position claim',
        thermal_step_s=.0625, end_s=30., records=rows)
    (OUT/'sampling-audit.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
