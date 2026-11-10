"""Project a saved, scoped dataset read into the existing comparison contract."""
import json


def comparison_evidence(record, source_file):
    selection = record['selection']
    mid, aid = selection['material_id'], selection['assay_id']
    aliases = {'enzyme_mimic_type': 'activity', 'activity_type': 'activity', 'ph': 'pH',
               'catalyst_concentration': 'material_dose'}
    facts = []
    for index, observation in enumerate(record['observations']):
        if observation.get('value') is None:
            continue
        field = observation['field'].split('.')[-1]
        value = observation['value']
        entries = [(aliases.get(field, field), value, observation.get('unit'))]
        if field == 'components' and isinstance(value, dict):
            role = value.get('role')
            name = {'substrate': 'substrate', 'co-substrate': 'co_substrate', 'buffer': 'buffer'}.get(role)
            dose = {'catalyst': 'material_dose', 'substrate': 'substrate_concentration', 'co-substrate': 'co_substrate_concentration', 'buffer': 'buffer_concentration'}.get(role)
            entries = []
            if name and value.get('substance'):
                entries.append((name, value['substance'], ''))
            concentration = value.get('concentration')
            if dose and concentration and concentration.get('value') is not None:
                entries.append((dose, concentration['value'], concentration.get('unit')))
        for projected_field, projected_value, unit in entries:
            fact = {
                'id': f'{aid}:{index}', 'material_id': mid, 'assay_id': aid,
                'field': projected_field,
                'value_raw': projected_value if isinstance(projected_value, str) else json.dumps(projected_value, ensure_ascii=False),
                'unit_raw': str(unit or ''), 'review': 'supported',
                'evidence': [{'file': source_file, 'locator': observation.get('observation_path') or f'/observations/{index}',
                              'quote': json.dumps(value, ensure_ascii=False), 'check': 'dataset_record_read',
                              'source_document_read': False, 'source_urls': observation.get('source', []),
                              'data_sha256': selection['data_sha256']}],
            }
            if len(entries) > 1:
                fact['id'] += ':' + projected_field
            if field == 'km':
                fact['kinetic_context'] = {'substrate': observation.get('substrate')}
            if field == 'vmax':
                fact['kinetic_context'] = {'normalization_basis': observation.get('normalization_basis')}
            facts.append(fact)
    return {'schema': 'highzyme.evidence.v1',
            'materials': [{'id': mid, 'name': selection['material_name'], 'version': selection.get('version_id') or ''}],
            'assays': [{'id': aid, 'material_id': mid, 'label': selection['material_name'] + ' · ' + aid}],
            'facts': facts, 'coverage': record.get('coverage', {})}
