import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image
from pint.errors import DimensionalityError

from highzyme.foundation_science import run
from highzyme.tools.tables import inspect_table


class ProjectCalculationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def table(self, name, headers, rows):
        file = self.root/name
        with file.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream); writer.writerow(headers); writer.writerows(rows)
        return str(file)

    def test_formulation_arithmetic_and_unit_errors(self):
        base = {'action': 'calculation', 'calculation': 'formulation'}
        result = run({**base, 'parameters': {'operation': 'dilution', 'stock_concentration': {'value': 10, 'unit': 'mM'},
            'target_concentration': {'value': 1, 'unit': 'mM'}, 'final_volume': {'value': 10, 'unit': 'mL'}}})
        self.assertAlmostEqual(result['data']['stock_volume']['value'], 1000)
        self.assertNotIn('files', result)
        mixture = {'operation': 'mixture', 'stocks': [{'label': 'H2O2', 'concentration': {'value': 10, 'unit': 'mM'}, 'volume': {'value': 10, 'unit': 'uL'}}], 'final_volume': {'value': 1, 'unit': 'mL'}}
        labelled = run({**base, 'parameters': mixture})
        del mixture['stocks'][0]['label']
        self.assertEqual(labelled['data'], run({**base, 'parameters': mixture})['data'])
        mixture['stocks'][0]['unexpected'] = 1
        with self.assertRaisesRegex(ValueError, r'stocks\[0\].*unsupported.*unexpected'):
            run({**base, 'parameters': mixture})
        with self.assertRaises(DimensionalityError):
            run({**base, 'parameters': {'operation': 'convert', 'quantity': {'value': 1, 'unit': 'mL'}, 'to_unit': 'mg'}})
        result = run({**base, 'parameters': {'operation': 'prepare_solution', 'formula': 'CuSO4.5H2O',
            'concentration': {'value': 10, 'unit': 'mM'}, 'final_volume': {'value': 100, 'unit': 'mL'}}})
        self.assertAlmostEqual(result['data']['amount']['value'], 1000)
        self.assertGreater(result['data']['mass']['value'], 249)
        self.assertLess(result['data']['mass']['value'], 250)

    def test_preview_is_bounded_and_analysis_validates_remaining_rows(self):
        file = self.table('large.csv', ['x', 'y'], ((i, 2*i+1) for i in range(200)))
        preview = inspect_table({'file': file})
        self.assertEqual(len(preview['preview']), 8)
        self.assertIsNone(preview['rows'])
        self.assertTrue(preview['truncated'])
        with open(file, 'a') as stream: stream.write('broken\n')
        with self.assertRaisesRegex(ValueError, 'column count'):
            run({'action': 'calculation', 'calculation': 'signal', 'file': file, 'operation': 'fit_calibration',
                 'columns': {'x': 'x', 'y': 'y'}, 'parameters': {'x_unit': 'uM', 'y_unit': 'a.u.'}})

    def test_calibration_reproduction_quantification_and_replot(self):
        file = self.table('calibration.csv', ['concentration', 'signal'], [(x, 2*x+1) for x in range(6)])
        request = {'action': 'calculation', 'calculation': 'signal', 'file': file, 'operation': 'fit_calibration',
                   'columns': {'x': 'concentration', 'y': 'signal'}, 'parameters': {'x_unit': 'uM', 'y_unit': 'a.u.'},
                   'output_prefix': str(self.root/'calibration'), 'language': 'zh'}
        before = Path(file).read_bytes(); result = run(request)
        self.assertAlmostEqual(result['data']['slope'], 2)
        self.assertAlmostEqual(result['data']['intercept'], 1)
        self.assertEqual(Path(file).read_bytes(), before)
        for output in result['files'].values(): self.assertTrue(Path(output).is_file())
        with Image.open(result['files']['png']) as image:
            self.assertAlmostEqual(image.info['dpi'][0], 600, places=1)
            self.assertGreater(image.width, 2000)
        import xml.etree.ElementTree as ET
        svg = ET.parse(result['files']['svg']).getroot()
        self.assertTrue(svg.findall('.//{http://www.w3.org/2000/svg}text'))
        self.assertAlmostEqual(float(svg.attrib['width'].removesuffix('pt'))/72*25.4, 89, places=3)
        fit_before = Path(result['files']['result']).read_bytes()
        redraw = run({'action': 'replot_analysis', 'file': result['files']['result'], 'output_prefix': str(self.root/'calibration'),
                      'labels': ['Measured', 'Fitted']})
        self.assertFalse(redraw['refitted'])
        self.assertEqual(Path(result['files']['result']).read_bytes(), fit_before)
        reproduced = subprocess.run([sys.executable, '-B', result['files']['script']], capture_output=True, text=True, encoding='utf-8', check=True)
        self.assertAlmostEqual(json.loads(reproduced.stdout)['data']['slope'], 2)
        samples = self.table('samples.csv', ['signal'], [(5,), (9,), (99,)])
        quantified = run({'action': 'calculation', 'calculation': 'signal', 'operation': 'quantify', 'file': samples,
                          'calibration_file': result['files']['result'], 'columns': {'signal': 'signal'}, 'parameters': {'y_unit': 'a.u.'}})
        self.assertEqual(quantified['data']['concentrations'], [2., 4., None])
        self.assertEqual(quantified['data']['within_range'], [True, True, False])

    def test_readout_and_correction_use_supplied_inputs(self):
        file = self.table('signals.csv', ['concentration', 'observed', 'factor'], [(0, 100, 1), (1, 60, 1.1), (3, 40, 1.2)])
        output = run({'action': 'calculation', 'calculation': 'signal', 'operation': 'linear_readout', 'file': file,
            'columns': {'concentrations': 'concentration'}, 'parameters': {'x_unit': 'uM', 'channels': [
                {'label': 'A', 'slope': 2, 'intercept': 1, 'range': [0, 2], 'y_unit': 'a.u.', 'source': 'synthetic'}]}})
        self.assertEqual(output['data']['channels'][0]['signals'], [1., 3., None])
        corrected = run({'action': 'calculation', 'calculation': 'signal', 'operation': 'quenching_correction', 'file': file,
            'columns': {'observed': 'observed', 'correction_factors': 'factor'}, 'parameters': {}})
        self.assertEqual(corrected['data']['corrected'], [100., 66., 48.])

    def test_colorimetry_measures_selected_pixels_and_saves_overlay(self):
        pixels = np.full((60, 100, 3), [200, 40, 10], dtype=np.uint8)
        pixels[:, 50:] = [10, 40, 200]
        file = self.root/'colors.png'; Image.fromarray(pixels).save(file)
        before = file.read_bytes()
        output = run({'action': 'calculation', 'calculation': 'colorimetry', 'files': [str(file)], 'source_labels': ['colors.png'],
                      'mode': 'region', 'region': [0, 0, .5, 1], 'output_prefix': str(self.root/'colors')})
        with open(output['files']['table'], encoding='utf-8-sig', newline='') as stream: row = next(csv.DictReader(stream))
        self.assertEqual([float(row[k]) for k in ('mean_r', 'mean_g', 'mean_b')], [200, 40, 10])
        self.assertEqual(int(row['pixels']), 3000)
        self.assertEqual(file.read_bytes(), before)
        self.assertTrue(Path(output['files']['roi_1']).is_file())
        blank = run({'action': 'calculation', 'calculation': 'colorimetry', 'files': [str(file)], 'mode': 'circle_rois'})
        self.assertEqual(blank['data']['images'][0]['status'], 'no_circles_detected')

    def test_network_matches_first_order_solution_and_conserves_total(self):
        parameters = {'operation': 'network', 'species': {'A': .001, 'B': 0}, 'reactions': [
            {'reactants': {'A': 1}, 'products': {'B': 1}, 'k': .1, 'parameter_basis': 'assumed'}], 'duration_s': 30, 'points': 65}
        result = run({'action': 'calculation', 'calculation': 'reaction', 'parameters': parameters,
                      'output_prefix': str(self.root/'network')})
        a, b = (np.array(result['data']['concentrations_M'][k]) for k in ('A', 'B'))
        np.testing.assert_allclose(a+b, .001, atol=1e-10)
        np.testing.assert_allclose(a, .001*np.exp(-.1*np.array(result['data']['time_s'])), rtol=3e-6)
        self.assertEqual(result['data']['parameter_basis'], ['assumed'])
        mm = run({'action': 'calculation', 'calculation': 'reaction', 'parameters': {'operation': 'michaelis_menten',
            'curves': [{'label': 'A', 'km_mM': .3, 'vmax_uM_s': 2.4, 'source': 'synthetic'}], 'substrate_mM': [0, .3, 3]}})
        self.assertAlmostEqual(mm['data']['curves'][0]['initial_rates_uM_s'][1], 1.2)

    def test_atomic_coordinate_formats_and_removed_database_action(self):
        file = self.root/'water.xyz'; file.write_text('3\nwater\nO 0 0 0\nH 0 0 .96\nH .9 0 -.2\n')
        result = run({'action': 'structure', 'file': str(file)})
        self.assertEqual(result['atom_count'], 3)
        self.assertEqual(result['site_occupancy_counts'], {'O': 1, 'H': 2})
        file.write_text(file.read_text()*2)
        with self.assertRaisesRegex(ValueError, 'single coordinate'):
            run({'action': 'structure', 'file': str(file)})
        with self.assertRaisesRegex(ValueError, 'Unknown scientific'):
            run({'action': 'knowledge', 'query': 'material'})

    def test_pdf_rendering_retains_original_page_and_hash(self):
        from pypdf import PdfWriter
        file = self.root/'paper.pdf'
        writer = PdfWriter(); writer.add_blank_page(width=216, height=144)
        with file.open('wb') as stream: writer.write(stream)
        before = file.read_bytes()
        output = run({'action': 'render_document', 'file': str(file), 'source_label': 'paper.pdf', 'pages': [1],
                      'dpi': 120, 'output_prefix': str(self.root/'paper-pages')})
        self.assertEqual(output['pages'][0]['locator'], 'PDF/page[1]')
        self.assertEqual(file.read_bytes(), before)
        with Image.open(output['files']['page_1']) as image: self.assertEqual(image.size, (360, 240))
        with self.assertRaisesRegex(ValueError, 'existing PDF'):
            run({'action': 'render_document', 'file': str(file), 'pages': [2], 'output_prefix': str(self.root/'invalid')})


if __name__ == '__main__': unittest.main()
