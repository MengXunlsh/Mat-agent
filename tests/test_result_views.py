"""Result presentation consumes saved numerical and structural data without refitting."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from highzyme.foundation_science import run
from highzyme.tools.result_views import result_view, structure_view
from highzyme.compute.qe_calculation import output_history

ROOT = Path(__file__).resolve().parents[1]


class ResultViewTests(unittest.TestCase):
    def test_identity_report_has_molecular_graph_and_original_numerical_mass(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = run(dict(action='identity', smiles='CC(=O)Oc1ccccc1C(=O)O', output_prefix=str(Path(temporary)/'identity')))
            view = result_view(dict(files=output['files']))
            self.assertEqual(view['kind'], 'identity')
            self.assertEqual(view['metrics'][1]['value'], output['molar_mass_g_mol'])
            self.assertEqual(output['formula'], 'C9H8O4')
            self.assertIn('<svg', Path(output['files']['depiction']).read_text(encoding='utf-8'))
            self.assertIn('![Molecular graph]', Path(output['files']['report']).read_text(encoding='utf-8'))

    def test_grouped_kinetics_uses_saved_estimates_and_keeps_input_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'rates.csv'
            with source.open('w', newline='') as stream:
                writer = csv.writer(stream); writer.writerow(['s', 'v', 'group'])
                writer.writerows((s, vmax*s/(.3+s), label) for label, vmax in [('A', 2), ('B', 3)] for s in [.05, .1, .3, 1, 3])
            output = run(dict(action='fit_kinetics', file=str(source), concentration_column='s', rate_column='v',
                              concentration_unit='mM', rate_unit='uM/s', group_columns=['group'], output_prefix=str(root/'rates')))
            file = Path(output['files']['result']); before = file.read_bytes()
            view = result_view(dict(files=output['files']))
            self.assertEqual(view['kind'], 'kinetics')
            self.assertEqual(len(view['charts']), 2)
            self.assertEqual(len(view['charts'][0]['series']), 4)
            self.assertAlmostEqual(view['tables'][0]['rows'][1]['vmax'], 3)
            self.assertEqual(file.read_bytes(), before)
            self.assertIn('![Initial-rate fit]', Path(output['files']['report']).read_text(encoding='utf-8'))

    def test_qe_history_matches_real_log_and_does_not_create_density_data(self):
        file = ROOT/'tests/fixtures/qe-silicon-scf.out'
        history = output_history(file.read_text(encoding='utf-8'))
        self.assertGreater(len(history['iterations']), 1)
        self.assertAlmostEqual(history['iterations'][-1]['energy_Ry'], -14.50260042)
        self.assertLess(history['iterations'][-1]['accuracy_Ry'], 1e-8)
        self.assertEqual(history['ionic_steps'], [])
        self.assertEqual(output_history('JOB DONE.')['iterations'], [])

    def test_structures_keep_real_coordinates_and_two_dimensional_graphs(self):
        value = structure_view((ROOT/'examples/general-research/qe-smoke/silicon.extxyz').read_bytes(), 'silicon.extxyz')
        self.assertEqual(value['atom_count'], 2)
        self.assertTrue(value['cell_angstrom'])
        self.assertEqual(value['symbols'], ['Si', 'Si'])
        from rdkit import Chem
        from rdkit.Chem import AllChem
        mol = Chem.MolFromSmiles('CC(=O)O'); AllChem.Compute2DCoords(mol)
        graph = structure_view(Chem.MolToMolBlock(mol).encode('utf-8'), 'acid.mol')
        self.assertEqual(graph['coordinate_dimension'], 2)
        self.assertIn('<svg', graph['depiction'])
        self.assertEqual(len(graph['positions_angstrom']), 4)

    def test_calibration_marks_excluded_samples_and_colorimetry_retains_roi(self):
        import numpy as np
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fit = dict(slope=2, intercept=1, range=[0, 5], x_unit='uM', y_unit='a.u.')
            output = run(dict(action='calculation', calculation='signal', parameters=dict(operation='quantify',
                         signal=[5, 99], calibration=fit, y_unit='a.u.'), output_prefix=str(root/'signal')))
            view = result_view(dict(files=output['files']))
            self.assertEqual(view['charts'][0]['series'][1]['x'], [2.])
            self.assertEqual(view['metrics'][-1]['value'], 1)
            self.assertEqual(output['data']['concentrations'], [2., None])
            image = root/'sample.png'; Image.fromarray(np.full((60, 100, 3), [150, 20, 10], dtype=np.uint8)).save(image)
            before = hashlib.sha256(image.read_bytes()).hexdigest()
            output = run(dict(action='calculation', calculation='colorimetry', files=[str(image)], mode='region',
                              region=[0, 0, .5, 1], output_prefix=str(root/'color')))
            view = result_view(dict(files=output['files']))
            row = view['tables'][0]['rows'][0]
            self.assertEqual(float(row['right']), .5)
            self.assertEqual(float(row['mean_r']), 150)
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
