"""Deterministic checks of explicitly supplied candidate stoichiometry and charge."""
from decimal import Decimal

from highzyme.tools.chemistry import formula_info


def check_candidate(request):
    checks, composition = [], None
    if request.get('formula'):
        try:
            composition = formula_info(request['formula'])['element_counts']
            checks.append({'name': 'formula', 'status': 'pass', 'detail': 'Explicit composition parsed; no crystal structure inferred.'})
        except ValueError as error:
            checks.append({'name': 'formula', 'status': 'unknown', 'detail': str(error)})
    species = request.get('species', [])
    if not isinstance(species, list) or len(species) > 64:
        raise ValueError('Supply at most 64 explicit species')
    if not species:
        checks.append({'name': 'charge_balance', 'status': 'unknown', 'detail': 'Counts and oxidation states are not supplied.'})
        return {'checks': checks, 'rejected': False, 'net_charge': None}
    counts, charge = {}, Decimal(0)
    for row in species:
        symbol = row['element']
        if formula_info(symbol)['element_counts'] != {symbol: 1}:
            raise ValueError('Species element must be an element symbol')
        count, oxidation = Decimal(str(row['count'])), Decimal(str(row['oxidation_state']))
        if not count.is_finite() or count <= 0 or not oxidation.is_finite():
            raise ValueError('Counts must be positive and oxidation states finite')
        counts[symbol] = counts.get(symbol, Decimal(0)) + count
        charge += count * oxidation
    target = Decimal(str(request.get('target_charge', 0)))
    if not target.is_finite():
        raise ValueError('Target charge must be finite')
    matched = composition is None or counts == {k: Decimal(str(v)) for k, v in composition.items()}
    if composition is not None:
        checks.append({'name': 'stoichiometry', 'status': 'pass' if matched else 'fail', 'detail': 'Compare declared species counts with the explicit formula.'})
    checks.append({'name': 'charge_balance', 'status': ('pass' if charge == target else 'fail') if matched else 'unknown',
                   'detail': 'Charge balance under the supplied oxidation-state model; not a stability or activity prediction.',
                   'net_charge': float(charge), 'target_charge': float(target)})
    return {'checks': checks, 'rejected': any(c['status'] == 'fail' for c in checks), 'net_charge': float(charge)}
