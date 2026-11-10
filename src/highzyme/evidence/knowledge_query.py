"""Additive query filters over stored facts; no scientific data is rewritten."""
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from .assay_projection import ASSAY_SCHEMA, SEARCH_ALIASES

EXTRA_FILTERS = {'material_class', 'application_major', 'application_subcategory',
                 'application_direction', 'record_kind', 'reactant', 'temperature_min',
                 'temperature_max', 'source_doi', 'required_fields'}
REQUIRED_FIELDS = {'km', 'vmax', 'catalyst_concentration'}
RECORD_KINDS = {'all', 'measurement', 'kinetic', 'unpaired_information'}


def norm(value):
    return unicodedata.normalize('NFKC', str('' if value is None else value)).strip().casefold()


def present(value):
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return norm(value) not in {'', 'no', 'none', 'null', 'nan', 'n/a', 'n.a.', 'nr', 'n.r.', 'unknown', 'not reported'}
    return True


def quantity(value):
    return isinstance(value, dict) and present(value.get('value')) and present(value.get('unit'))


def concentration_unit(value):
    unit = norm(value).replace('µ', 'u').replace('μ', 'u').replace(' ', '')
    for mark in ('·', '⋅', '×', '∙', '•', '^', '{', '}'):
        unit = unit.replace(mark, '')
    unit = unit.replace('−', '-').replace('–', '-').replace('mcg', 'ug')
    if unit in {'m', 'mm', 'um', 'nm', 'pm', '%(w/v)', '%(v/v)', '%v/v'}:
        return True
    return bool(re.fullmatch(r'(?:[pnumk]?g(?:fe|ru|ir|pt|au|co|ni|cu|mn|ag|ce|pd|metal)?|[pnumk]?mol)(?:/[pnum]?l|[pnum]?l-1)', unit))


def decimal(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def celsius(observation):
    if not isinstance(observation, dict):
        return None
    number = decimal(observation.get('value'))
    unit = norm(observation.get('unit')).replace(' ', '')
    if number is None:
        return None
    if unit in {'°c', 'c', 'degc', 'celsius', 'degreecelsius', 'degreescelsius'}:
        return number
    if unit in {'k', 'kelvin'}:
        return number - Decimal('273.15')
    return None


def validate(filters):
    required = filters.get('required_fields', [])
    if not isinstance(required, list) or len(required) > 3 or any(not isinstance(k, str) or k not in REQUIRED_FIELDS for k in required):
        raise ValueError('Required fields must be selected from km, vmax and catalyst_concentration')
    if filters.get('record_kind', 'all') not in RECORD_KINDS:
        raise ValueError('Unsupported knowledge record kind')
    for key in ('temperature_min', 'temperature_max'):
        if key in filters and decimal(filters[key]) is None:
            raise ValueError('Temperature bounds must be finite Celsius numbers')
    if 'temperature_min' in filters and 'temperature_max' in filters and decimal(filters['temperature_min']) > decimal(filters['temperature_max']):
        raise ValueError('Minimum temperature must not exceed maximum temperature')


def text_match(value, expected):
    left, right = norm(value), norm(expected)
    return SEARCH_ALIASES.get(right, right) in SEARCH_ALIASES.get(left, left)


def application_matches(observation, filters):
    value = observation.get('value')
    if not isinstance(value, dict):
        return False
    return all(norm(value.get(key)) == norm(filters[name])
               for name, key in [('application_major', 'major_category'), ('application_subcategory', 'subcategory')]
               if name in filters) and ('application_direction' not in filters or
               all(term in norm(value.get('direction')) for term in norm(filters['application_direction']).split()))


def result_present(scoped, key, *, unit=False):
    return any(quantity(o) if unit else present(o.get('value'))
               for o in (scoped.get('reported_results', {}).get(key) or []))


def normal_doi(value):
    value = norm(value).removeprefix('https://doi.org/').removeprefix('http://doi.org/').removeprefix('doi:').strip()
    return re.sub(r'\.s\d+$', '', value)


def record_type_matches(record, kind):
    expected = 'measurement' if kind == 'kinetic' else kind
    return expected not in ('measurement', 'unpaired_information') or record.get('record_type') == expected


def matches(record, scoped, object_fields, filters, source_dois=()):
    kind = filters.get('record_kind', 'all')
    if not record_type_matches(record, kind):
        return False
    if kind == 'kinetic' and not any(result_present(scoped, k) for k in ('km', 'vmax')):
        return False
    if 'material_class' in filters and not any(norm(o.get('value')) == norm(filters['material_class'])
            for o in (object_fields.get('material_features', {}).get('material_class') or [])):
        return False
    if any(k in filters for k in ('application_major', 'application_subcategory', 'application_direction')) and not any(
            application_matches(o, filters) for o in (object_fields.get('application_information', {}).get('applications') or [])):
        return False
    if 'source_doi' in filters:
        dois = {normal_doi(d) for d in source_dois}
        for groups in (scoped, object_fields):
            for fields in groups.values():
                for observations in fields.values():
                    for observation in observations or []:
                        for source in observation.get('source', []):
                            if re.match(r'https?://doi\.org/', source, re.I):
                                dois.add(normal_doi(source))
        if normal_doi(filters['source_doi']) not in dois:
            return False
    required = filters.get('required_fields', [])
    if any(not result_present(scoped, key, unit=True) for key in required if key in {'km', 'vmax'}):
        return False
    conditions = scoped.get('reaction_conditions', {})
    needs_stage = any(k in filters for k in ('reactant', 'temperature_min', 'temperature_max')) or 'catalyst_concentration' in required
    if not needs_stage:
        return True
    if record.get('assay_schema') == ASSAY_SCHEMA:
        stages = record.get('reaction_conditions', {}).get('stages', [])
    else:
        # Legacy scopes are already split by assay ID and source in the reader.
        stages = [{'ph': o} for o in conditions.get('ph', [])] or [{}]
        for stage in stages:
            stage['_legacy'] = True
            stage['temperatures'] = conditions.get('temperature', [])
            stage['components'] = [dict(role=role, substance=o.get('value'))
                                   for key, role in [('substrate', 'substrate'), ('co_substrate', 'co-substrate')]
                                   for o in conditions.get(key, [])]
            stage['components'] += [dict(role='catalyst', concentration=o)
                                    for o in conditions.get('nanozyme_concentration', [])]
    for stage in stages:
        components = stage.get('components', [])
        if 'reactant' in filters and not any(c.get('role') in {'substrate', 'co-substrate'} and text_match(c.get('substance'), filters['reactant']) for c in components):
            continue
        if 'substrate' in filters and not any(c.get('role') == 'substrate' and text_match(c.get('substance'), filters['substrate']) for c in components):
            continue
        if 'ph' in filters and norm((stage.get('ph') or {}).get('value')) != norm(filters['ph']):
            if decimal((stage.get('ph') or {}).get('value')) is None or decimal((stage.get('ph') or {}).get('value')) != decimal(filters['ph']):
                continue
        if any(k in filters for k in ('temperature_min', 'temperature_max')):
            values = [celsius(o) for o in stage.get('temperatures', [stage.get('temperature')])]
            if not any(value is not None and ('temperature_min' not in filters or value >= decimal(filters['temperature_min']))
                       and ('temperature_max' not in filters or value <= decimal(filters['temperature_max'])) for value in values):
                continue
        if 'catalyst_concentration' in required and not any(c.get('role') == 'catalyst' and quantity(c.get('concentration'))
                                                          and concentration_unit(c['concentration']['unit']) for c in components):
            continue
        return True
    return False


def add_facets(obj, classes, applications, activities):
    for observation in obj.get('material_features', {}).get('material_class') or []:
        if isinstance(observation.get('value'), str) and present(observation['value']):
            classes.add(observation['value'])
    for observation in obj.get('application_information', {}).get('applications') or []:
        value = observation.get('value')
        if isinstance(value, dict) and present(value.get('major_category')):
            subcategories = applications.setdefault(value['major_category'], set())
            if present(value.get('subcategory')):
                subcategories.add(value['subcategory'])
    activity = obj.get('reaction_conditions', {}).get('activity_type')
    if isinstance(activity, dict) and isinstance(activity.get('value'), str) and present(activity['value']):
        activities.add(activity['value'])


def preview(scoped, object_fields):
    """Small native-field overview, not an extra scientific record."""
    conditions = scoped.get('reaction_conditions', {})
    def values(rows):
        return list(dict.fromkeys(str(o['value']) for o in rows if present(o.get('value'))))[:4]
    return {'activity': values(conditions.get('activity_type', conditions.get('enzyme_mimic_type', []))),
            'substrates': values(conditions.get('substrate', [])),
            'material_classes': values(object_fields.get('material_features', {}).get('material_class', [])),
            'results': [key for key in ('km', 'vmax', 'kcat', 'specific_activity') if result_present(scoped, key)]}


def content_preview(scoped, object_fields):
    """Bounded stored values for local browsing, never a new measurement."""
    rows = []
    for group, fields in {**scoped, **object_fields}.items():
        for field, observations in fields.items():
            # Preserve native structured stages; skip compatibility duplicates.
            values = [o for o in observations if not o.get('_compatibility_alias') and present(o.get('value'))]
            for observation in values[:2]:
                value = observation['value']
                if len(str(value)) > 1600:
                    continue
                rows.append({'field': group + '.' + field, 'value': value,
                             'unit': observation.get('unit'),
                             'path': observation.get('_feature_path'),
                             'source': observation.get('source', observation.get('sources', []))})
            if len(rows) >= 24:
                return rows[:24]
    return rows
