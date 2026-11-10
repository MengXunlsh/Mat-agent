"""Bounded declared-input kinetics and optical analysis; never a DFT surrogate."""
from __future__ import annotations

import math
import re
from importlib.metadata import version

import numpy as np
from scipy.integrate import solve_ivp
from scipy.stats import linregress


def number(value, *, minimum=None, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('A finite numeric value is required')
    if (minimum is not None and value < minimum) or (positive and value <= 0):
        raise ValueError('Numeric value is outside its physical domain')
    return float(value)


def vector(values, *, minimum=None, limit=256):
    if not isinstance(values, list) or not 1 <= len(values) <= limit:
        raise ValueError('Supply a nonempty bounded list of numeric values')
    return np.array([number(x, minimum=minimum) for x in values])


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError('Missing or unsupported calculation fields')


def completed(data, method, libraries):
    return {'status': 'COMPLETED', 'data': data,
            'method': {'name': method, 'libraries': {lib: version(lib) for lib in libraries}},
            'limitations': ['Computed from declared inputs; reported parameters, derived values and assumptions retain their separate provenance.',
                            'This calculation is not new experimental evidence or a quantum-chemical simulation.']}


def reaction_simulation(request):
    op = request.get('operation')
    if op in {'michaelis_menten', 'reciprocal_parameters'}:
        fields(request, {'operation', 'curves', 'substrate_mM'}, {'time_s'})
        concentrations = vector(request['substrate_mM'], minimum=0)
        curves = request['curves']
        if not isinstance(curves, list) or not 1 <= len(curves) <= 8:
            raise ValueError('Supply one to eight declared kinetic curves')
        output = []
        for curve in curves:
            if op == 'reciprocal_parameters':
                fields(curve, {'label', 'slope', 'intercept', 'x_scale_per_M', 'y_scale_s_per_M', 'source'})
                intercept = number(curve['intercept'], positive=True)
                slope = number(curve['slope'], minimum=0)
                km = slope / intercept / number(curve['x_scale_per_M'], positive=True) * 1000
                vmax = 1e6 / (intercept * number(curve['y_scale_s_per_M'], positive=True))
            else:
                fields(curve, {'label', 'km_mM', 'vmax_uM_s', 'source'})
                km, vmax = number(curve['km_mM'], positive=True), number(curve['vmax_uM_s'], positive=True)
            if km <= 0 or not isinstance(curve['label'], str) or not isinstance(curve['source'], str):
                raise ValueError('A kinetic curve requires positive Km, label and an explicit input source')
            rates = vmax * concentrations / (km + concentrations)
            row = {'label': curve['label'], 'source': curve['source'], 'km_mM': km,
                   'vmax_uM_s': vmax, 'initial_rates_uM_s': rates.tolist()}
            if 'time_s' in request:
                duration = number(request['time_s'], positive=True)
                if duration > 86400:
                    raise ValueError('Simulation duration exceeds one day')
                substrate = float(max(concentrations)) * 1000
                times = np.linspace(0, duration, 65)
                def rhs(t, y):
                    return [-vmax * max(y[0], 0) / (km * 1000 + max(y[0], 0))]
                solution = solve_ivp(rhs, (0, duration), [substrate], t_eval=times,
                                     method='BDF', rtol=1e-8, atol=1e-10)
                if not solution.success or np.min(solution.y) < -1e-7:
                    raise ValueError('Kinetic integration failed')
                row['time_course'] = {'time_s': times.tolist(), 'substrate_uM': np.maximum(solution.y[0], 0).tolist(),
                    'converted_substrate_uM': (substrate - np.maximum(solution.y[0], 0)).tolist(),
                    'assumptions': ['Constant active catalyst, well-mixed solution, Michaelis-Menten substrate depletion only.',
                                    'No deactivation, oxygen limitation, product inhibition or signal-reduction chemistry is supplied.']}
            output.append(row)
        comparisons = []
        if len(output) == 2:
            a, b = output
            denominator = a['vmax_uM_s'] - b['vmax_uM_s']
            crossing = ((b['vmax_uM_s'] * a['km_mM'] - a['vmax_uM_s'] * b['km_mM']) / denominator
                        if abs(denominator) > 1e-15 else None)
            if crossing is not None and crossing <= 0:
                crossing = None
            comparisons = [{'label': a['label'] + ' / ' + b['label'], 'positive_crossover_mM': crossing,
                'initial_rate_ratios': [float(x/y) if y > 0 else None for x, y in zip(a['initial_rates_uM_s'], b['initial_rates_uM_s'])],
                'interpretation': 'Compare rates at the same declared substrate concentration; Km alone does not rank catalytic rates.'}]
        return completed({'substrate_mM': concentrations.tolist(), 'curves': output, 'comparisons': comparisons},
                         'Michaelis-Menten declared-parameter analysis and optional substrate-depletion ODE', ['scipy', 'numpy'])
    if op != 'network':
        raise ValueError('Choose michaelis_menten, reciprocal_parameters or network')
    fields(request, {'operation', 'species', 'reactions', 'duration_s'}, {'points'})
    species, reactions = request['species'], request['reactions']
    if not isinstance(species, dict) or not 1 <= len(species) <= 12 or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', k) for k in species):
        raise ValueError('Declare one to twelve simple species identifiers and initial concentrations in M')
    if not isinstance(reactions, list) or not 1 <= len(reactions) <= 16:
        raise ValueError('Declare one to sixteen reactions')
    names = list(species)
    initial = np.array([number(species[k], minimum=0) for k in names])
    parsed, laws = [], []
    for row in reactions:
        fields(row, {'reactants', 'products', 'k', 'parameter_basis'})
        for side in ('reactants', 'products'):
            mapping = row[side]
            if not isinstance(mapping, dict) or any(k not in names or type(v) is not int or not 1 <= v <= 4 for k, v in mapping.items()):
                raise ValueError('Stoichiometry must refer to declared species with integer coefficients 1..4')
        if not row['reactants'] and not row['products']:
            raise ValueError('Empty reactions are invalid')
        if row['parameter_basis'] not in {'reported', 'derived', 'assumed'}:
            raise ValueError('Classify each rate constant as reported, derived or assumed')
        rate = number(row['k'], minimum=0)
        parsed.append([row['products'].get(name, 0)-row['reactants'].get(name, 0) for name in names])
        laws.append((row['reactants'], rate))
    stoich = np.asarray(parsed, dtype=float).T
    duration = number(request['duration_s'], positive=True)
    points = request.get('points', 65)
    if duration > 86400 or type(points) is not int or not 2 <= points <= 256:
        raise ValueError('Duration or output grid exceeds its bounded domain')
    calls = [0]
    def rhs(t, y):
        calls[0] += 1
        if calls[0] > 20000:
            raise ValueError('Declared network exceeds the integration work limit')
        concentrations = dict(zip(names, np.maximum(y, 0)))
        rates = [rate * math.prod(concentrations[k]**power for k, power in reactants.items())
                 for reactants, rate in laws]
        return stoich @ rates
    times = np.linspace(0, duration, points)
    solution = solve_ivp(rhs, (0, duration), initial, t_eval=times, method='BDF', rtol=1e-7, atol=1e-12)
    if not solution.success or not np.isfinite(solution.y).all() or np.min(solution.y) < -max(1e-10, max(initial)*1e-5):
        raise ValueError('Network integration did not produce a usable nonnegative solution')
    return completed({'time_s': times.tolist(), 'concentrations_M': {k: np.maximum(solution.y[i], 0).tolist() for i, k in enumerate(names)},
        'parameter_basis': [r['parameter_basis'] for r in reactions],
        'rate_constant_units': ['M^' + str(1-sum(r['reactants'].values())) + '/s' for r in reactions],
        'solver': {'success': True, 'method': 'BDF', 'rhs_evaluations': calls[0]},
        'assumptions': ['Declared mass-action network only; species labels do not establish chemical mechanisms.',
                        'All initial concentrations are M and time is seconds. Rate constants use M^(1-reaction order)/s.']},
        'Declared stoichiometric mass-action network with SciPy BDF integration', ['scipy', 'numpy'])


def signal_analysis(request):
    op = request.get('operation')
    if op == 'linear_readout':
        fields(request, {'operation', 'channels', 'concentrations', 'x_unit'}, {'thresholds'})
        x = vector(request['concentrations'], minimum=0)
        if not isinstance(request['channels'], list) or not 1 <= len(request['channels']) <= 4:
            raise ValueError('Supply one to four calibrated channels')
        rows = []
        for channel in request['channels']:
            fields(channel, {'label', 'slope', 'intercept', 'range', 'y_unit', 'source'})
            domain = vector(channel['range'], limit=2)
            if len(domain) != 2 or domain[0] >= domain[1]:
                raise ValueError('Calibration requires an increasing source range')
            slope, intercept = number(channel['slope']), number(channel['intercept'])
            valid = (x >= domain[0]) & (x <= domain[1])
            rows.append({**channel, 'signals': [float(slope*v+intercept) if good else None for v, good in zip(x, valid)],
                         'within_source_range': valid.tolist(), 'direction': 'increasing' if slope > 0 else 'decreasing' if slope < 0 else 'constant'})
        data = {'concentrations': x.tolist(), 'x_unit': request['x_unit'], 'channels': rows,
                'interpretation': 'Evaluation of supplied calibration equations, not a new fit or independent detection test.'}
        if 'thresholds' in request:
            bounds = vector(request['thresholds'], minimum=0, limit=2)
            if len(bounds) != 2 or np.any(np.diff(bounds) <= 0):
                raise ValueError('Supply two increasing thresholds for three concentration bins')
            data.update(thresholds=bounds.tolist(), bins=np.where(x < bounds[0], 0, np.where(x <= bounds[1], 1, 2)).tolist(),
                        threshold_intervals=['x < lower', 'lower <= x <= upper', 'x > upper'],
                        threshold_meaning='Declared concentration bins; not regulatory or safety conclusions.')
        return completed(data, 'Declared linear calibration evaluation and concentration bins', ['numpy'])
    if op == 'quenching_correction':
        fields(request, {'operation', 'observed', 'correction_factors', 'source'})
        observed = vector(request['observed'], minimum=0)
        factors = vector(request['correction_factors'], minimum=0)
        if len(observed) != len(factors) or observed[0] <= 0 or factors[0] <= 0 or np.any(factors <= 0):
            raise ValueError('Matched positive correction factors and an unquenched first reference are required')
        corrected = observed*factors
        eobs, ecor = 1-observed/observed[0], 1-corrected/corrected[0]
        fraction = [float((a-b)/a) if a > 1e-12 else None for a, b in zip(eobs, ecor)]
        return completed({'observed': observed.tolist(), 'corrected': corrected.tolist(),
            'observed_quenching': eobs.tolist(), 'corrected_quenching': ecor.tolist(),
            'removed_quenching_fraction': fraction, 'source': request['source'],
            'basis': 'Fcor=Fobs*CF; Eobs=1-Fobs/Fobs0; Ecor=1-Fcor/Fcor0; fraction=(Eobs-Ecor)/Eobs.',
            'geometry': 'Correction factors are supplied, not inferred from an unspecified optical geometry.'},
            'Fluorescence correction from explicitly supplied correction factors', ['numpy'])
    if op == 'fit_calibration':
        fields(request, {'operation', 'x', 'y', 'x_unit', 'y_unit', 'source'})
        x, y = vector(request['x']), vector(request['y'])
        if len(x) != len(y) or len(x) < 3 or np.ptp(x) == 0:
            raise ValueError('At least three paired observations at distinct x are required')
        fit = linregress(x, y)
        residual = y-(fit.slope*x+fit.intercept)
        if np.ptp(y) == 0:
            raise ValueError('A constant signal has no defined correlation-based R squared')
        return completed({'x': x.tolist(), 'y': y.tolist(), 'slope': float(fit.slope), 'intercept': float(fit.intercept), 'r_squared': float(fit.rvalue**2),
            'residuals': residual.tolist(), 'n': len(x), 'x_unit': request['x_unit'], 'y_unit': request['y_unit'],
            'source': request['source'], 'range': [float(min(x)), float(max(x))],
            'validation': 'Fit to supplied observations only; no independent or held-out validation claimed.'},
            'SciPy ordinary least squares linear calibration', ['scipy', 'numpy'])
    raise ValueError('Choose linear_readout, quenching_correction or fit_calibration')
