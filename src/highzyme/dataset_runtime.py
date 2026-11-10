"""Persistent, read-only bridge to the registered structured nanozyme release."""
import json
from collections import OrderedDict
from pathlib import Path
import sys

from highzyme.evidence.structured_knowledge import StructuredKnowledgeStore


def record_summary(record):
    """Keep every selected value; verbose lineage remains available on demand."""
    omitted = {'trace', 'sources_resolved', 'material_id', 'version_id', 'record_id', 'assay_id'}
    return {**record, 'detail': 'values',
            'observations': [{k: v for k, v in observation.items() if k not in omitted}
                             for observation in record['observations']],
            'provenance_detail': 'Use detail=full, optionally with fields, for original quotes and lineage. Saved source artifacts retain the complete record.'}


class DatasetStore(StructuredKnowledgeStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queries = OrderedDict()

    def _matching_rows(self, datasets, terms, source_dataset, filters, material_id):
        releases = [(name, str(paths['data']), paths.get('release_id'), paths.get('version'), self._verify_release(paths)) for name, paths in datasets.items()]
        key = json.dumps([releases, terms, source_dataset, filters, material_id], sort_keys=True, ensure_ascii=False)
        if key not in self.queries:
            rows = list(super()._matching_rows(datasets, terms, source_dataset, filters, material_id))
            self.queries[key] = rows
            while len(self.queries) > 3:
                self.queries.popitem(last=False)
        self.queries.move_to_end(key)
        return iter(self.queries[key])

    def _hash(self, path, *, verify=False):
        # The local release is verified once per file fingerprint, not per UI page.
        return super()._hash(path, verify=False)


class DatasetRuntime:
    def __init__(self):
        self.registry = None
        self.store = None
        self.spaces = {}

    def run(self, request):
        registry = Path(request['registry']).resolve()
        if registry != self.registry:
            self.store = DatasetStore(registry.parent, registry.name)
            self.registry = registry
        action = request['action']
        if action == 'catalog':
            value = self.store.catalog()
            if request.get('section'):
                keys = {
                    'overview': ['dataset', 'release_id', 'materials', 'versions', 'measurement_records', 'kinetic_records', 'record_type_counts'],
                    'filters': ['dataset', 'facets', 'origin_material_counts'],
                    'fields': ['dataset', 'available_fields', 'field_labels'],
                }[request['section']]
                return {'datasets': [{k: d[k] for k in keys} for d in value['datasets']]}
            return value
        if action == 'material':
            limit, offset = request.get('limit', 5), request.get('offset', 0)
            if type(limit) is not int or not 1 <= limit <= 20:
                raise ValueError('Material record limit must be 1 to 20')
            value = self.store.browse(material_id=request['material_id'], record_offset=offset, limit=1)
            for group in value['groups']:
                group['hits'] = group['hits'][:limit]
                group['record_page'] = {'offset': offset, 'limit': limit,
                    'next_offset': offset + len(group['hits']) if offset + len(group['hits']) < group['count'] else None}
            return value
        if action == 'space':
            from highzyme.evidence.material_space import MaterialSpaceStore
            resource = request.get('analysis_registry')
            if not resource:
                raise ValueError('Connect a material-space resource in dataset settings first')
            entry = Path(resource).resolve()
            if entry.name != 'material-space-registry.json' or entry.parent.name != 'protocol':
                raise ValueError('Select the material-space-registry.json in the analysis resource protocol directory')
            root = entry.parent.parent
            if root not in self.spaces:
                self.spaces[root] = MaterialSpaceStore(root)
            value = self.spaces[root].run(request.get('options', {}))
            active = next(iter(self.store._datasets().values()))
            hashes = self.store._verify_release(active)
            if value['source']['database_release'] != active['release_id'] or self.spaces[root].manifest['source']['resource_hashes'] != hashes:
                raise ValueError('Material-space resource does not match the connected dataset release')
            return value
        if action in ('search', 'browse'):
            options = {k: v for k, v in request.items() if k not in ('registry', 'action', 'id')}
            return getattr(self.store, action)(**options)
        if action == 'read':
            detail = request.get('detail', 'values')
            if detail not in ('values', 'full'):
                raise ValueError('Choose values or full record detail')
            result = self.store.read(request['selection_id'], fields=request.get('fields'), share_with_agent=True, complete=True)
            if not result['read']:
                return {key: result[key] for key in ('status', 'read', 'selection', 'observations', 'unknown_fields', 'coverage')}
            result = self.store.agent_projection(result)
            return result if detail == 'full' else record_summary(result)
        raise ValueError('Unknown dataset operation')


def main():
    runtime = DatasetRuntime()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = {'result': runtime.run(request)}
        except Exception as error:
            result = {'error': str(error)}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
