import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from highzyme.dataset_runtime import DatasetRuntime


class DatasetRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='highzyme-query-cache-')
        self.root = Path(self.temp.name)
        records = [dict(key=str(i), record_id='r'+str(i), record_type='measurement' if i % 2 else 'unpaired_information',
            reaction_conditions={'enzyme_mimic_type': [{'value': 'peroxidase', 'source': []}]}, reported_results={}) for i in range(7)]
        material = dict(schema='highzyme.material.reported.parallel.v2', material_id='m', material_name='Fe3O4', aliases=[], sources={}, default_sources=[],
            material_features={}, application_information={}, variants=[dict(key='v', version_id='v', records=records)], material_information_records=[])
        assets = dict(data='data.jsonl', trace='trace.jsonl', mapping='mapping.jsonl')
        hashes = {}
        for key, filename in assets.items():
            raw = (json.dumps(material)+'\n') if key == 'data' else ''
            (self.root/filename).write_text(raw, encoding='utf-8')
            hashes[key] = hashlib.sha256((self.root/filename).read_bytes()).hexdigest()
        self.registry = self.root/'database_registry.json'
        self.registry.write_text(json.dumps(dict(path_base='directory containing this registry', active_release='test', releases=[dict(release_id='test', layout='integrated', schema=material['schema'], **assets, expected_sha256=hashes)])), encoding='utf-8')
        self.runtime = DatasetRuntime()

    def tearDown(self):
        self.temp.cleanup()

    def query(self, action='search', **args):
        return self.runtime.run(dict(registry=str(self.registry), action=action, **args))

    def test_pages_and_limits_reuse_query_and_keep_original_order(self):
        first = self.query(limit=2)
        cached = next(iter(self.runtime.store.queries.values()))
        second = self.query(limit=3, offset=2)
        self.assertIs(next(iter(self.runtime.store.queries.values())), cached)
        self.assertEqual(first['matching_assay_scopes'], 7)
        self.assertEqual([r['record_id'] for r in first['hits']+second['hits']], ['r0','r1','r2','r3','r4'])
        self.assertEqual(self.query(limit=2)['hits'], first['hits'])
        self.assertEqual(self.query(limit=3, activity='CAT')['matching_assay_scopes'], 0)
        self.assertEqual(self.query(limit=3, activity='POD')['matching_assay_scopes'], 7)

    def test_browse_cache_has_measurement_order_and_readable_selection_locations(self):
        first = self.query('browse', page_by='records', limit=2)
        second = self.query('browse', page_by='records', limit=3, offset=2)
        self.assertEqual([h['record_id'] for g in first['groups']+second['groups'] for h in g['hits']], ['r1','r3','r5','r0','r2'])
        for hit in first['groups'][0]['hits']:
            self.assertIn(hit['selection_id'], self.runtime.store._selections)
        self.assertEqual(self.query('browse', page_by='records', limit=2), first)

    def test_changed_source_never_reuses_cached_matches(self):
        self.query(limit=2)
        with (self.root/'data.jsonl').open('a') as stream:
            stream.write('\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.query(limit=2, offset=2)

    def test_complete_reads_keep_late_quantities_and_summary_values(self):
        material = json.loads((self.root/'data.jsonl').read_text(encoding='utf-8'))
        material['variants'][0]['records'][0]['reported_results'] = {
            'km': [{'value': str(i), 'unit': 'mM', 'source': [], 'note': 'original detail ' * 150}
                   for i in range(90)], 'vmax': [{'value': '0.5', 'unit': 'uM/s', 'source': []}]}
        (self.root/'data.jsonl').write_text(json.dumps(material)+'\n', encoding='utf-8')
        registry = json.loads(self.registry.read_text(encoding='utf-8'))
        registry['releases'][0]['expected_sha256']['data'] = hashlib.sha256((self.root/'data.jsonl').read_bytes()).hexdigest()
        self.registry.write_text(json.dumps(registry), encoding='utf-8')
        selection = self.query(limit=1)['hits'][0]['selection_id']
        summary = self.query('read', selection_id=selection)
        full = self.query('read', selection_id=selection, detail='full')
        self.assertGreater(len(full['observations']), 80)
        self.assertFalse(full['coverage']['truncated'])
        self.assertEqual(summary['coverage'], full['coverage'])
        self.assertEqual([(v['field'],v['value'],v.get('unit')) for v in summary['observations']],
                         [(v['field'],v['value'],v.get('unit')) for v in full['observations']])
        self.assertEqual(full['observations'][-1]['value'], '0.5')
        self.assertNotIn('trace', summary['observations'][0])
        targeted = self.query('read', selection_id=selection, fields=['reported_results.vmax'], detail='full')
        self.assertEqual(len(targeted['observations']), 1)
        group = self.query('read', selection_id=selection, fields=['reported_results'])
        self.assertEqual(len(group['observations']), 91)
        empty = self.query('read', selection_id=selection, fields=['unknown.field'])
        self.assertFalse(empty['read'])
        self.assertEqual(empty['unknown_fields'], ['unknown.field'])
