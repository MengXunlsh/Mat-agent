import unittest

from highzyme.foundation_science import run


class CandidateChecksTests(unittest.TestCase):
    def test_mixed_valence_and_inconsistent_charge(self):
        rows = [{'element': 'Fe', 'count': 1, 'oxidation_state': 2},
                {'element': 'Fe', 'count': 2, 'oxidation_state': 3},
                {'element': 'O', 'count': 4, 'oxidation_state': -2}]
        value = run({'action': 'candidate_check', 'formula': 'Fe3O4', 'species': rows})
        self.assertFalse(value['rejected'])
        self.assertEqual(value['net_charge'], 0)
        bad = run({'action': 'candidate_check', 'formula': 'Fe3O4', 'species': [
            {'element': 'Fe', 'count': 3, 'oxidation_state': 3}, rows[-1]]})
        self.assertTrue(bad['rejected'])
        self.assertEqual(bad['net_charge'], 1)

    def test_missing_states_are_unknown_not_passed(self):
        value = run({'action': 'candidate_check', 'formula': 'Fe3O4'})
        self.assertFalse(value['rejected'])
        self.assertEqual(value['checks'][-1]['status'], 'unknown')

    def test_species_count_mismatch_is_not_charge_evidence(self):
        value = run({'action': 'candidate_check', 'formula': 'Fe3O4', 'species': [
            {'element': 'Fe', 'count': 2, 'oxidation_state': 3},
            {'element': 'O', 'count': 3, 'oxidation_state': -2}]})
        self.assertTrue(value['rejected'])
        self.assertEqual(value['checks'][-1]['status'], 'unknown')

    def test_explicit_ion_charge_and_invalid_counts(self):
        value = run({'action': 'candidate_check', 'formula': 'NH4', 'target_charge': 1, 'species': [
            {'element': 'N', 'count': 1, 'oxidation_state': -3}, {'element': 'H', 'count': 4, 'oxidation_state': 1}]})
        self.assertFalse(value['rejected'])
        with self.assertRaises(ValueError):
            run({'action': 'candidate_check', 'species': [{'element': 'Fe', 'count': 0, 'oxidation_state': 2}]})
