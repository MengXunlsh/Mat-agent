"""Conservative, purpose-specific comparison of declared assay contexts."""
from __future__ import annotations

import math
from highzyme.tools.formulation import quantity, number
from highzyme.tools.assay_inputs import classify_inputs, is_missing

TEXT_FIELDS = {'material', 'activity', 'substrate', 'buffer', 'readout', 'normalization', 'dose_basis', 'co_substrate'}
QUANTITY_FIELDS = {'temperature': 'degC', 'time': 'minute', 'material_dose': None,
                   'substrate_concentration': None, 'buffer_concentration': None, 'wavelength': 'nm', 'co_substrate_concentration': None}
REQUIRED = (TEXT_FIELDS - {'co_substrate'}) | {'pH', 'temperature', 'time', 'material_dose',
                         'substrate_concentration', 'buffer_concentration'}
FIELDS = REQUIRED | {'wavelength', 'co_substrate', 'co_substrate_concentration'}


def compare_field(field, a, b):
    """Compare declared values on the same dimensional basis without alias inference."""
    if field in QUANTITY_FIELDS or field in ('km', 'vmax'):
        qa, qb = quantity(a), quantity(b)
        if qa.dimensionality != qb.dimensionality:
            return False, False
        return math.isclose(float(qa.magnitude), float(qb.to(qa.units).magnitude), rel_tol=1e-9, abs_tol=0), True
    if field == 'pH':
        return math.isclose(number(a), number(b), rel_tol=0, abs_tol=1e-9), True
    return a.strip().casefold() == b.strip().casefold(), True


def compare_assays(request):
    if not isinstance(request, dict) or set(request) - {'purpose', 'records', 'varied_field', 'assess_missing'}:
        raise ValueError('Use purpose, records, optional varied_field and assess_missing')
    if type(request.get('assess_missing', False)) is not bool:
        raise ValueError('assess_missing must be boolean')
    purpose = request.get('purpose')
    if purpose not in {'material_activity', 'condition_effect', 'transfer'}:
        raise ValueError('Purpose must be material_activity, condition_effect or transfer')
    varied = request.get('varied_field')
    if (purpose == 'condition_effect' and varied not in FIELDS - {'material'}) or (purpose != 'condition_effect' and varied is not None):
        raise ValueError('condition_effect requires one explicit varied_field; other purposes accept none')
    records = request.get('records')
    if not isinstance(records, list) or len(records) != 2:
        raise ValueError('Compare exactly two source-labelled records')
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) - FIELDS - {'id', 'source', 'preparation'}:
            raise ValueError('Unsupported assay field')
        if any(not isinstance(record.get(k), str) or not 1 <= len(record[k]) <= 1000 for k in ('id', 'source')):
            raise ValueError('Each record needs id and source (declared provenance, not independently verified)')
        for key, value in record.items():
            if is_missing(value) or key in {'id', 'source', 'preparation'}:
                continue
            if key in TEXT_FIELDS:
                if not isinstance(value, str) or not 1 <= len(value.strip()) <= 300:
                    raise ValueError('Text assay fields must be nonempty strings')
            elif key == 'pH':
                number(value)
            else:
                q = quantity(value, QUANTITY_FIELDS[key])
                if key in {'material_dose', 'substrate_concentration', 'buffer_concentration', 'co_substrate_concentration'}:
                    if not (q.check('[mass]/[length]**3') or q.check('[substance]/[length]**3')) or q.magnitude <= 0:
                        if key == 'material_dose' and q.check('[length]**3'):
                            return {'status': 'REFUSED', 'reason': 'material_dose requires final concentration, not added volume.',
                                'data': {}, 'recovery': {
                                    'target': f'/records/{index}/material_dose',
                                    'next_tool': 'formulation', 'operation': 'mixture',
                                    'required_inputs': ['reported stock concentration', 'added volume', 'final assay volume'],
                                    'reuse': 'Bind the completed P_ /data/final_concentration here using tool_value, then retry assay_compare.',
                                    'missing_input': 'If any required input is absent, omit material_dose and report it as missing; do not infer a volume.'},
                                'limitations': ['No condition-comparison result was produced.']}
                        raise ValueError('Dose/concentration requires positive mass or molar concentration')
                elif key in {'time', 'wavelength'} and q.magnitude <= 0:
                    raise ValueError('Time/wavelength must be positive')
                elif key == 'temperature' and q.to('kelvin').magnitude <= 0:
                    raise ValueError('Temperature must be above absolute zero')
    if records[0]['id'] == records[1]['id']:
        raise ValueError('Record IDs must differ')
    expected = {'material'} if purpose == 'material_activity' else {varied} if varied else set()
    required_fields = set(REQUIRED)
    # POD cannot be considered matched solely by matching its chromogenic substrate.
    if any(str(r.get('activity', '')).casefold() in {'pod', 'pod-like', 'peroxidase', 'peroxidase-like', '过氧化物酶'} for r in records):
        required_fields.update({'co_substrate', 'co_substrate_concentration'})
    information, calculations = classify_inputs(records, require_review=request.get('assess_missing', False), required_fields=required_fields)
    if calculations or any(r['state'] == 'NOT_ASSESSED' for r in information):
        return {'status': 'CLARIFY', 'reason': 'INPUT_PREPARATION_REQUIRED',
            'data': {'input_readiness': information},
            'recovery': {'calculations': calculations,
                'next_step': 'For each calculations entry, pass only tool_id, request, input_bindings to run_tool, one call at a time. Then bind each completed P_ /data/final_concentration to its target and retry this comparison. For NOT_ASSESSED inspect the permitted source and populate preparation. This is tool preparation, not a request for missing user input.',
                'boundary': 'No final concentration or comparison has been calculated yet. MISSING_PREREQUISITES means absent from declared preparation, not independently verified absent from the whole paper.'},
            'limitations': ['Reported operands can yield calculated quantities; not explicitly printed does not mean unknowable. No guessed operands or experimental results.']}
    missing, differences, matched = [], [], []
    for field in sorted(FIELDS):
        a, b = (r.get(field) for r in records)
        a = None if is_missing(a) else a
        b = None if is_missing(b) else b
        required = field in required_fields or any(v is not None for v in (a, b))
        if a is None or b is None:
            if required:
                missing.append({'field': field, 'records': [r['id'] for r, v in zip(records, (a, b)) if v is None]})
            continue
        equal, comparable = compare_field(field, a, b)
        if equal:
            matched.append(field)
        else:
            differences.append({'field': field, 'left': a, 'right': b,
                'role': 'intended_variable' if field in expected and comparable else 'confounder_or_mismatch',
                'unit_basis_comparable': comparable})
    confounded = any(d['role'] == 'confounder_or_mismatch' for d in differences)
    outcome = ('NOT_DIRECTLY_COMPARABLE' if confounded else 'INSUFFICIENT_CONTEXT' if missing else
               'DECLARED_CONTEXT_MATCHES')
    return {'status': 'COMPLETED', 'data': {'purpose': purpose, 'outcome': outcome, 'checked_field_scope': sorted(FIELDS),
            'matched_fields': matched, 'differences': differences, 'missing_fields': missing, 'input_readiness': information,
            'next_step': 'Resolve mismatched conditions before numerical pooling or transfer.' if confounded else
                         'Recover missing conditions before comparison.' if missing else
                         'Check replicates, uncertainty and measurement validity before ranking performance.'},
        'source': {'kind': 'declared_records', 'records': [{'id': r['id'], 'source': r['source']} for r in records]},
        'method': 'Explicit field comparison with dimensional conversion; no learned similarity score',
        'limitations': ['Inputs and source labels are supplied, not independently verified.',
                       'Matching fields do not prove equal activity, causality, mechanism or transferable performance.',
                       'Text aliases are not silently equated. Different dose bases require explicit composition information.',
                       'Only the listed fields are checked; oxygen/light, mixing, path length, matrix and measurement uncertainty may require separate review.']}
