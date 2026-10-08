"""Small physical-input and active-boundary functions shared by solver and checks."""
import numpy as np


def tools_may_release(time_s, arc_end_s, maximum_C, policy):
    return time_s - arc_end_s >= policy['minimum_post_arc_hold_s'] and maximum_C < policy['part_max_temperature_exclusive_C']


def annotate_start_permissions(records, final_process):
    minimum, first_maximum = final_process['start_temperature_C']
    subsequent_maximum = final_process['interpass_limit_C']
    return [{**record, 'control_minimum_C': minimum, 'control_maximum_C': first_maximum if record['pass'] == 0 else subsequent_maximum,
             'temperature_permission_pass': minimum <= record['second_layer_current_max_C'] <= (first_maximum if record['pass'] == 0 else subsequent_maximum)} for record in records]


def active_exterior_faces(active, owners):
    first = active[owners[:, 0]]
    second = np.zeros(len(owners), dtype=bool)
    shared = owners[:, 1] >= 0
    second[shared] = active[owners[shared, 1]]
    return first ^ second


def specific_enthalpy(query, table):
    """J/kg above entering-metal20C reference, including the declared latent heat."""
    data = table['temperature_dependent']
    knots = np.asarray(data['temperatures_c'], float)
    cp = np.asarray(data['specific_heat_j_kgk'], float)
    prefix = np.r_[0, np.cumsum(np.diff(knots) * (cp[:-1] + cp[1:]) / 2)]

    def integral(values):
        index = np.clip(np.searchsorted(knots, values, side='right') - 1, 0, len(knots) - 2)
        dx = np.minimum(values, knots[-1]) - knots[index]
        return prefix[index] + cp[index] * dx + .5 * np.diff(cp)[index] / np.diff(knots)[index] * dx ** 2 + np.maximum(values - knots[-1], 0) * cp[-1]

    fusion = table['fusion_enthalpy']
    fraction = lambda values: np.clip((values - fusion['solidus_C']) / (fusion['liquidus_C'] - fusion['solidus_C']), 0, 1)
    query = np.asarray(query, float)
    return integral(query) - integral(np.array(20.)) + fusion['latent_heat_J_kg'] * (fraction(query) - fraction(np.array(20.)))


def validate_arc_prefix_metadata(identity, expected, state_digest):
    """Reject a changed accepted state or changed physical/discretization inputs."""
    if identity.get('schema') != 'ring-final-accepted-arc-prefix-v1' or identity.get('state_npz_sha256') != state_digest:
        raise RuntimeError('accepted arc checkpoint state does not match its identity')
    if identity.get('mesh_cache_key') != expected['mesh_cache_key']:
        raise RuntimeError('accepted arc prefix CAD/process/discretization differs')
    previous = identity['thermal_result']
    for name in ('process_version', 'arc_dt_s', 'declared_source', 'material_inputs'):
        if previous.get(name) != expected[name]:
            raise RuntimeError(f'accepted arc prefix {name} differs from requested input')
