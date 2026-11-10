import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from highzyme.foundation_science import run
from highzyme.tools.initial_rate import fit_initial_rates


class InitialRateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def table(self, scale=1, rates=None):
        x = np.array([0, .05, .1, .2, .4, .8, 1.6]) * scale
        y = 2.4 * scale * x / (.3 * scale + x) if rates is None else rates
        file = self.root / 'rates.csv'
        with file.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['substrate', 'rate', 'sd'])
            writer.writerows(zip(x, y, np.full(len(x), .02 * scale)))
        return {'file': str(file), 'concentration_column': 'substrate', 'rate_column': 'rate',
                'concentration_unit': 'mM', 'rate_unit': 'uM/s'}

    def test_known_parameters_and_small_units(self):
        for scale in (1, 1e-9):
            with self.subTest(scale=scale):
                result = fit_initial_rates({**self.table(scale), 'sigma_column': 'sd'})
                self.assertAlmostEqual(result['km'] / scale, .3, places=7)
                self.assertAlmostEqual(result['vmax'] / scale, 2.4, places=7)
                self.assertTrue(result['weighted'])

    def test_invalid_data_is_not_silently_dropped(self):
        request = self.table()
        for patch in ({'concentration_column': 'missing'}, {'rate_unit': ''}, {'rate_column': 'substrate'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                fit_initial_rates({**request, **patch})
        request = self.table(rates=[0, 1, 2, float('nan'), 3, 4, 5])
        with self.assertRaisesRegex(ValueError, 'finite'):
            fit_initial_rates(request)

    def test_xlsx_requires_explicit_sheet_and_previews_columns(self):
        from openpyxl import Workbook
        file = self.root / 'rates.xlsx'
        book = Workbook()
        for sheet in (book.active, book.create_sheet('other')):
            sheet.append(['substrate', 'rate'])
            for x in [.05, .1, .2, .4, .8]:
                sheet.append([x, 2.4*x/(.3+x)])
        book.save(file)
        preview = run({'action': 'inspect_table', 'file': str(file)})
        self.assertEqual(preview['columns'], ['substrate', 'rate'])
        self.assertEqual(len(preview['sheets']), 2)
        request = {**self.table(), 'file': str(file)}
        with self.assertRaisesRegex(ValueError, 'Select an XLSX sheet'):
            fit_initial_rates(request)
        self.assertAlmostEqual(fit_initial_rates({**request, 'sheet': 'other'})['km'], .3, places=7)

    def test_real_exports_and_reproduction(self):
        request = {**self.table(), 'action': 'fit_kinetics', 'output_prefix': str(self.root / 'initial-rate'), 'language': 'zh'}
        before = Path(request['file']).read_bytes()
        output = run(request)
        self.assertEqual(len(output['files']), 8)
        for file in output['files'].values():
            self.assertGreater(Path(file).stat().st_size, 100)
        self.assertIn('初始速率', Path(output['files']['report']).read_text(encoding='utf-8'))
        self.assertEqual(before, Path(request['file']).read_bytes())
        completed = subprocess.run([sys.executable, '-B', output['files']['script'], output['files']['request']], capture_output=True, text=True, encoding='utf-8', check=True)
        reproduced = json.loads(completed.stdout)
        self.assertAlmostEqual(reproduced['fit']['km'], output['fit']['km'], places=10)
        self.assertAlmostEqual(reproduced['fit']['vmax'], output['fit']['vmax'], places=10)
        self.assertEqual(reproduced['fit']['source']['file'], Path(output['files']['data']).name)

    def test_grouped_fit_reproduction_and_replot(self):
        file = self.root / 'grouped.csv'
        with file.open('w', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(['material', 'pH', 'substrate', 'rate'])
            for name, km, vmax, ph in [('A', .3, 2.4, 4), ('B', .6, 1.8, 5)]:
                for x in [.02, .05, .1, .2, .4, .8, 1.6]:
                    writer.writerow([name, ph, x, vmax*x/(km+x)])
        request = {'action': 'fit_kinetics', 'file': str(file), 'concentration_column': 'substrate', 'rate_column': 'rate',
                   'concentration_unit': 'mM', 'rate_unit': 'uM/s', 'group_columns': ['material'], 'context_columns': ['pH'],
                   'output_prefix': str(self.root / 'group-fit'), 'plot_layout': 'panels'}
        result = run(request)
        self.assertEqual(len(result['files']), 9)
        self.assertAlmostEqual(result['fit']['groups'][0]['km'], .3, places=7)
        self.assertAlmostEqual(result['fit']['groups'][1]['vmax'], 1.8, places=7)
        numerical = Path(result['files']['result']).read_bytes()
        plot = run({'action': 'replot_kinetics', 'file': result['files']['result'], 'output_prefix': str(self.root / 'group-fit'),
                    'plot_layout': 'overlay', 'labels': ['Material A', 'Material B']})
        self.assertFalse(plot['refitted'])
        self.assertEqual(numerical, Path(result['files']['result']).read_bytes())
        reproduced = subprocess.run([sys.executable, '-B', result['files']['script'], result['files']['request']], capture_output=True, text=True, encoding='utf-8', check=True)
        self.assertAlmostEqual(json.loads(reproduced.stdout)['fit']['groups'][1]['km'], .6, places=7)
        with self.assertRaisesRegex(ValueError, 'Condition varies'):
            run({**request, 'group_columns': []})
        file.write_text(file.read_text().replace('A,4,0.02', 'A,6,0.02'))
        with self.assertRaisesRegex(ValueError, 'Condition varies'):
            run(request)


if __name__ == '__main__':
    unittest.main()
