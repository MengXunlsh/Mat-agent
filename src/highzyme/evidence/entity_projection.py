"""Compatibility views for stable entities with external management metadata.

Stored scientific data has no legacy source keys or local V/R aliases. Those
are restored only in the reader's temporary view, never written back to data.
"""
from copy import deepcopy

ENTITY_SCHEMA = 'highzyme.entities.source-linked.v1'


def project_entities(material, management):
    if material.get('entity_schema') != ENTITY_SCHEMA:
        return material
    mid = material['material_id']
    if management.get('material_id') != mid:
        raise ValueError('Entity management material identity mismatch')
    view = deepcopy(material)
    meta = management['material_metadata']
    view['sources'] = deepcopy(meta.get('sources', {}))
    view['default_sources'] = deepcopy(meta.get('default_sources', []))
    # Original display labels are query aliases, not confirmed chemical aliases.
    view['_historical_search_names'] = [meta.get('material_name', ''), *management.get('unconfirmed_names', [])]
    view['_identity_review'] = deepcopy(management.get('boundary_findings', []))
    versions = management['versions']
    records = management['records']
    for version in view.get('variants', []):
        vm = versions[version['version_id']]
        version['key'] = vm['metadata']['key']
        version['_scope_status'] = vm['scope_status']
    parents = [(v['version_id'], r) for v in view.get('variants', []) for r in v.get('records', [])]
    parents += [(None, r) for r in view.get('material_information_records', [])]
    for vid, record in parents:
        rm = records[record['record_id']]
        if rm['version_id'] != vid:
            raise ValueError('Entity management record parent mismatch')
        legacy = rm['metadata']
        for key in ('key', 'sources', 'association'):
            if key in legacy:
                record[key] = deepcopy(legacy[key])
        record['_scope_status'] = rm['scope_status']
    return view
