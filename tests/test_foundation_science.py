"""Offline contract checks for the native Harness scientific-reader bridge."""
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from highzyme.foundation_science import run


class FoundationScienceTests(unittest.TestCase):
    def test_structure_retains_cell_and_omits_large_coordinate_arrays(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'NaCl.cif'
            file.write_text('''data_test
_cell_length_a 5.64
_cell_length_b 5.64
_cell_length_c 5.64
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na1 Na 0 0 0
Cl1 Cl 0.5 0.5 0.5
''', encoding='utf-8')
            result = run({'action': 'structure', 'file': str(file)})
            self.assertEqual(result['atom_count'], 2)
            self.assertTrue(result['periodic_cell_present'])
            self.assertEqual(result['site_occupancy_counts'], {'Na': 1, 'Cl': 1})
            self.assertNotIn('positions_angstrom', result)

    def test_project_document_keeps_exact_source_locator(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'source.docx'
            with ZipFile(file, 'w') as archive:
                archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>TMB at pH 4.0</w:t></w:r></w:p></w:body></w:document>')
            result = run({'action': 'document', 'file': str(file), 'root': folder})
            self.assertTrue(result['read'])
            self.assertEqual(result['excerpts'][0]['text'], 'TMB at pH 4.0')
            self.assertIn('paragraph', result['excerpts'][0]['locator'])


if __name__ == '__main__':
    unittest.main()
