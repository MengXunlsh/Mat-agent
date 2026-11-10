from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from highzyme.foundation_science import run
from highzyme.tools.research_evidence import validate_dataset


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / 'source.md').write_text('Synthetic fixture, not a literature result.\nA: Km = 0.30 mM; pH = 4.0\nB: Km = 300 uM; pH = 5.0\n', encoding='utf-8')
        self.data = {'schema': 'highzyme.evidence.v1', 'title': 'Synthetic evidence',
            'materials': [{'id': 'm1', 'name': 'A'}, {'id': 'm2', 'name': 'B'}],
            'assays': [{'id': 'a1', 'material_id': 'm1', 'label': 'A assay'}, {'id': 'a2', 'material_id': 'm2', 'label': 'B assay'}], 'facts': []}
        for i, values in enumerate([('0.30', 'mM', '4.0'), ('300', 'uM', '5.0')], 1):
            for field, value, unit in [('km', values[0], values[1]), ('pH', values[2], '')]:
                self.data['facts'].append({'id': f'f{i}-{field}', 'material_id': f'm{i}', 'assay_id': f'a{i}', 'field': field,
                    'value_raw': value, 'unit_raw': unit, 'review': 'supported',
                    'evidence': [{'file': 'source.md', 'locator': f'lines[{i+1}]', 'quote': value}]})

    def save(self, data=None):
        draft = self.root / 'draft.json'
        draft.write_text(json.dumps(data or self.data), encoding='utf-8')
        return run({'action': 'save_evidence', 'file': str(draft), 'root': str(self.root), 'output_prefix': str(self.root / 'evidence'), 'language': 'zh'})

    def compare(self, **patch):
        saved = self.save()
        return run({'action': 'compare_evidence', 'selections': [{'file': saved['files']['data'], 'assay_ids': ['a1', 'a2']}],
            'fields': ['km', 'pH', 'temperature'], 'output_prefix': str(self.root / 'comparison'), 'language': 'zh', **patch})

    def test_sources_associations_and_revisions(self):
        saved = self.save()
        data = json.loads(Path(saved['files']['data']).read_text(encoding='utf-8'))
        self.assertEqual(len(data['facts'][0]['evidence'][0]['source_sha256']), 64)
        self.assertEqual(data['facts'][0]['evidence'][0]['check'], 'text_match')
        for patch in ({'material_id': 'm2'}, {'value_raw': 1}, {'evidence': [{'file': 'source.md', 'locator': 'lines[2]', 'quote': 'invented value'}]}):
            bad = deepcopy(self.data); bad['facts'][0].update(patch)
            with self.assertRaises(ValueError):
                self.save(bad)
        (self.root / 'source.md').write_text('Changed source', encoding='utf-8')
        with self.assertRaises(ValueError):
            validate_dataset(data, self.root)

    def test_docx_locator_and_visual_status(self):
        with zipfile.ZipFile(self.root / 'source.docx', 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Km = 0.30 mM</w:t></w:r></w:p></w:body></w:document>')
        self.data['facts'][0]['evidence'] = [{'file': 'source.docx', 'locator': 'word/document.xml/paragraph[1]', 'quote': '0.30'}]
        self.save()
        self.data['facts'][0]['evidence'][0].update(basis='visual', quote='Figure transcription')
        data = validate_dataset(self.data, self.root)
        self.assertEqual(data['facts'][0]['evidence'][0]['check'], 'source_located_visual_not_checked')

    def test_comparison_units_missing_conditions_and_conflicts(self):
        result = self.compare()
        self.assertEqual([f['state'] for f in result['pairs'][0]['fields']], ['matched', 'different', 'missing'])
        report = Path(result['files']['report']).read_text(encoding='utf-8')
        self.assertIn('缺失', report)
        self.data['facts'][2]['unit_raw'] = 'mg/mL'
        self.assertEqual(self.compare()['pairs'][0]['fields'][0]['state'], 'unit_mismatch')
        self.data['facts'][2]['unit_raw'] = 'nonexistent-unit'
        self.assertEqual(self.compare()['pairs'][0]['fields'][0]['state'], 'needs_interpretation')
        self.data['facts'][2]['review'] = 'conflict'
        self.assertEqual(self.compare()['pairs'][0]['fields'][0]['state'], 'unreviewed')
        self.data['facts'].append({**deepcopy(self.data['facts'][0]), 'id': 'duplicate-value'})
        self.assertEqual(self.compare()['pairs'][0]['fields'][0]['state'], 'multiple_values')

    def test_field_aliases_resolve_to_existing_facts(self):
        result = self.compare(fields=['reported_results.Km', 'ph'])
        self.assertEqual([r['field'] for r in result['pairs'][0]['fields']], ['km','pH'])
        self.assertEqual([r['state'] for r in result['pairs'][0]['fields']], ['matched','different'])

    def test_truncated_saved_snapshot_is_not_treated_as_unreported(self):
        files = []
        for index, truncated in enumerate([True, False]):
            file = self.root/f'record-{index}.json'
            file.write_text(json.dumps({'schema': 'highzyme.dataset-record.v1',
                'selection': {'material_id': f'm{index}', 'assay_id': f'a{index}', 'material_name': 'Fe3O4', 'data_sha256': 'a'*64},
                'observations': [{'field': 'reaction_conditions.activity', 'value': 'POD', 'source': []}], 'coverage': {'truncated': truncated}}), encoding='utf-8')
            files.append({'file': str(file), 'assay_ids': [f'a{index}']})
        result = run({'action': 'compare_evidence', 'selections': files, 'fields': ['km'],
                      'output_prefix': str(self.root/'snapshot-compare'), 'language': 'zh'})
        self.assertEqual(result['pairs'][0]['fields'][0]['state'], 'not_read')
        self.assertIn('读取不完整', Path(result['files']['report']).read_text(encoding='utf-8'))

    def test_dataset_components_and_kinetic_context_survive_comparison(self):
        files = []
        for index, substrate in enumerate(['TMB', 'H2O2']):
            file = self.root/f'components-{index}.json'
            file.write_text(json.dumps({'schema': 'highzyme.dataset-record.v1',
                'selection': {'material_id': f'm{index}', 'assay_id': f'a{index}', 'material_name': 'Fe3O4', 'data_sha256': 'a'*64},
                'observations': [
                    {'field': 'reaction_conditions.stages.components', 'value': {'role': 'substrate', 'substance': substrate, 'concentration': {'value': '0.1–1', 'unit': 'mM'}}, 'source': []},
                    {'field': 'reaction_conditions.stages.components', 'value': {'role': 'catalyst', 'concentration': {'value': '.05', 'unit': 'mg/mL'}}, 'source': []},
                    {'field': 'reported_results.km', 'value': '.2', 'unit': 'mM', 'substrate': substrate, 'source': []},
                    {'field': 'reported_results.vmax', 'value': '1', 'unit': 'uM/s', 'normalization_basis': None, 'source': []}]}), encoding='utf-8')
            files.append({'file': str(file), 'assay_ids': [f'a{index}']})
        result = run({'action': 'compare_evidence', 'selections': files, 'fields': ['substrate', 'substrate_concentration', 'material_dose', 'km', 'vmax'], 'output_prefix': str(self.root/'components-compare')})
        saved = json.loads(Path(result['files']['data']).read_text(encoding='utf-8'))
        self.assertEqual(saved['series'][0]['values']['material_dose'][0]['unit_raw'], 'mg/mL')
        self.assertEqual(saved['series'][0]['values']['substrate_concentration'][0]['value_raw'], '0.1–1')
        states = {v['field']: v['state'] for v in result['pairs'][0]['fields']}
        self.assertEqual(states['material_dose'], 'matched')
        self.assertEqual(states['km'], 'needs_interpretation')
        self.assertEqual(states['vmax'], 'needs_interpretation')


if __name__ == '__main__':
    unittest.main()
