"""Classify declared concentration inputs without inventing or calculating them."""
from copy import deepcopy
from highzyme.tools.formulation import quantity

CONCENTRATIONS = {'material_dose', 'substrate_concentration', 'buffer_concentration', 'co_substrate_concentration'}
MISSING = {'unknown', 'not reported', 'not stated', 'not stated in excerpt', 'not provided',
           'not specified', 'nr', 'n/a', '未报道', '未知', '未提供'}


def is_missing(value):
    return value is None or (isinstance(value, str) and value.strip().casefold() in MISSING)


def preparation_state(recipe):
    """Check available operands and dimensions; leave actual arithmetic to formulation."""
    if not isinstance(recipe, dict) or set(recipe) - {'stocks', 'final_volume'}:
        raise ValueError('preparation uses stocks and final_volume; omit unavailable operands')
    missing = []
    volume = recipe.get('final_volume')
    final = None if volume is None else quantity(volume, 'mL', positive=True)
    if final is None:
        missing.append('final_volume')
    stocks = recipe.get('stocks', [])
    if not isinstance(stocks, list) or len(stocks) > 30:
        raise ValueError('preparation stocks must be a list of at most 30 same-solute aliquots')
    if not stocks:
        missing.append('stocks')
    dimensionality, added = None, 0
    for i, stock in enumerate(stocks):
        if not isinstance(stock, dict) or set(stock) - {'concentration', 'volume'}:
            raise ValueError('Each preparation stock accepts concentration and volume')
        for key in ('concentration', 'volume'):
            if stock.get(key) is None:
                missing.append(f'stocks/{i}/{key}')
                continue
            q = quantity(stock[key], 'mL' if key == 'volume' else None, positive=True)
            if key == 'volume':
                added += q.magnitude
            else:
                if not (q.check('[mass]/[length]**3') or q.check('[substance]/[length]**3')):
                    raise ValueError('Preparation requires stock mass or molar concentration')
                if dimensionality is not None and dimensionality != q.dimensionality:
                    raise ValueError('Preparation mixes mass and molar concentration bases; explicit identity conversion is needed')
                dimensionality = q.dimensionality
    if final is not None and added > final.magnitude:
        raise ValueError('Known aliquot volumes exceed final volume')
    return missing


def classify_inputs(records, *, require_review=False, required_fields=()):
    rows, calls = [], []
    for index, record in enumerate(records):
        prep = record.get('preparation', {})
        if not isinstance(prep, dict) or set(prep) - CONCENTRATIONS:
            raise ValueError('preparation maps concentration fields to stocks/final_volume')
        targets = set(prep) | (CONCENTRATIONS & set(required_fields) if require_review else set())
        for field in sorted(targets):
            row = {'record': record['id'], 'field': field, 'target': f'/records/{index}/{field}'}
            missing = preparation_state(prep[field]) if field in prep else None
            if not is_missing(record.get(field)):
                row['state'] = 'VALUE_SUPPLIED'
            elif missing is None:
                row.update(state='NOT_ASSESSED', next_step='Inspect the permitted passage for stock concentration, aliquot and final volume. Supply preparation, using {} only when none are available.')
            elif missing:
                row.update(state='MISSING_PREREQUISITES', missing_inputs=missing,
                           next_step='Retain these missing operands; do not borrow conditions from another assay.')
            else:
                row['state'] = 'READY_TO_CALCULATE'
                calls.append({'target': row['target'], 'tool_id': 'formulation',
                    'request': {'operation': 'mixture', **deepcopy(prep[field])},
                    'input_binding_prefix': f'/records/{index}/preparation/{field}',
                    'reuse_path': '/data/final_concentration'})
            rows.append(row)
    return rows, calls


def carry_calculation_bindings(result, audit):
    """Reuse checked operand links, not output-only audit fields or permissions."""
    fields = {'target', 'kind', 'record_id', 'locator', 'quote', 'value_text', 'path', 'reason'}
    for call in result.get('recovery', {}).get('calculations', []):
        prefix = call['input_binding_prefix']
        call['input_bindings'] = []
        for binding in audit.get('bindings', []):
            if binding['target'].startswith(prefix + '/'):
                clean = {k: deepcopy(v) for k, v in binding.items() if k in fields}
                clean['target'] = binding['target'][len(prefix):]
                call['input_bindings'].append(clean)
